// Copyright (C) 2026 Matthew Jennings
// Licensed under the Apache License, Version 2.0; see
// test_deidentify_redaction_review_page.py.
//
// Runs the redaction review app's page script against a minimal stand-in
// for the browser: elements, a canvas that draws nothing, a fake clock, and
// a fake server whose responses each scenario controls. It drives the
// handlers that the script registers, as a reviewer's pointer and keys
// would, and checks what the script sends the server and shows.
//
//     node _redaction_review_page.cjs APP_JS SCENARIO
//
// It exits non-zero, with the failed assertion, if the scenario fails.
"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const ROWS = 40;
const COLUMNS = 60;
const FRAMES = 3;
const PROPOSAL = [5, 5, 10, 20];
const CANVAS = { left: 0, top: 0, width: 800, height: 600 };
const SCRUBBER = { left: 0, top: 0, width: 800, height: 28 };

// The browser.

class ClassList {
  constructor() {
    this.names = new Set();
  }
  add(...names) {
    for (const name of names) this.names.add(name);
  }
  remove(...names) {
    for (const name of names) this.names.delete(name);
  }
  toggle(name, force) {
    const on = force === undefined ? !this.names.has(name) : Boolean(force);
    if (on) this.names.add(name);
    else this.names.delete(name);
    return on;
  }
  contains(name) {
    return this.names.has(name);
  }
}

function dispatchTo(listeners, type, target, fields) {
  const event = {
    type,
    target,
    defaultPrevented: false,
    preventDefault() {
      this.defaultPrevented = true;
    },
    ...fields,
  };
  for (const listener of listeners[type] || []) listener(event);
  return event;
}

function drawingContext() {
  // Every method draws nothing; every property can be set.
  return new Proxy(
    {},
    {
      get: (target, key) => (key in target ? target[key] : () => {}),
      set: (target, key, value) => {
        target[key] = value;
        return true;
      },
    },
  );
}

class Element {
  constructor(tag, id = "", rect = CANVAS) {
    this.tagName = tag.toUpperCase();
    this.id = id;
    this.rect = rect;
    this.classList = new ClassList();
    this.listeners = {};
    this.children = [];
    this.attributes = {};
    this.textContent = "";
    this.className = "";
    this.title = "";
    this.disabled = false;
    this.checked = false;
    this.open = false;
    this.width = 0;
    this.height = 0;
  }
  addEventListener(type, listener) {
    (this.listeners[type] ||= []).push(listener);
  }
  dispatch(type, fields = {}) {
    return dispatchTo(this.listeners, type, this, fields);
  }
  setAttribute(name, value) {
    this.attributes[name] = value;
  }
  replaceChildren(...children) {
    this.children = children;
  }
  append(...children) {
    this.children.push(...children);
  }
  focus() {}
  setPointerCapture() {}
  getBoundingClientRect() {
    return this.rect;
  }
  getContext() {
    return drawingContext();
  }
  showModal() {
    this.open = true;
  }
  close() {
    if (!this.open) return;
    this.open = false;
    this.dispatch("close");
  }
}

class HTMLInputElement extends Element {}

class ImageData {
  constructor(width, height) {
    this.width = width;
    this.height = height;
    this.data = new Uint8ClampedArray(width * height * 4);
  }
}

const IDS = [
  "pack", "progress", "saved", "summary-button", "help-button", "instances", "undecided-only",
  "instance-title", "frame-label", "seen-label", "window-button", "blackout-button", "fit-button",
  "loading", "verdict-label", "undecide-button", "reject-button", "confirm-button", "regions",
  "clear-frame-button", "toast", "help-close", "summary-counts", "crops", "summary-saved",
  "attest-command", "summary-close",
];

function makeDocument() {
  const elements = new Map(IDS.map((id) => [id, new Element("div", id)]));
  elements.set("canvas", new Element("canvas", "canvas", CANVAS));
  elements.set("scrubber", new Element("canvas", "scrubber", SCRUBBER));
  elements.set("help", new Element("dialog", "help"));
  elements.set("summary", new Element("dialog", "summary"));
  const dialogs = [elements.get("help"), elements.get("summary")];
  const listeners = {};
  return {
    elements,
    body: new Element("body"),
    visibilityState: "visible",
    getElementById: (id) => {
      assert.ok(elements.has(id), `the page has no element ${id}`);
      return elements.get(id);
    },
    createElement: (tag) => new Element(tag),
    createTextNode: (text) => ({ textContent: text }),
    querySelector: (selector) => {
      assert.equal(selector, "dialog[open]");
      return dialogs.find((dialog) => dialog.open) || null;
    },
    querySelectorAll: (selector) => {
      assert.equal(selector, "dialog");
      return dialogs;
    },
    addEventListener(type, listener) {
      (listeners[type] ||= []).push(listener);
    },
    dispatch(type, fields = {}) {
      return dispatchTo(listeners, type, this, fields);
    },
  };
}

// Time: timers run only when a scenario advances the clock.

function makeClock() {
  let now = 0;
  let next = 1;
  const timers = new Map();
  const settle = async () => {
    for (let i = 0; i < 25; i += 1) await new Promise((resolve) => setImmediate(resolve));
  };
  return {
    setTimeout: (callback, delay = 0) => {
      const id = next;
      next += 1;
      timers.set(id, { at: now + Math.max(0, delay), callback });
      return id;
    },
    clearTimeout: (id) => timers.delete(id),
    settle,
    async advance(milliseconds) {
      const end = now + milliseconds;
      for (;;) {
        await settle();
        let due = null;
        for (const [id, timer] of timers) {
          if (timer.at <= end && (due === null || timer.at < due.timer.at)) due = { id, timer };
        }
        if (due === null) break;
        timers.delete(due.id);
        now = due.timer.at;
        due.timer.callback();
      }
      now = end;
      await settle();
    },
  };
}

// The server.

function response(status, body, headers = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    headers: { get: (name) => (name in headers ? String(headers[name]) : null) },
    json: async () => body,
    arrayBuffer: async () => body,
  };
}

function instance(position) {
  return {
    position,
    frames: FRAMES,
    rows: ROWS,
    columns: COLUMNS,
    reason: "synthetic",
    proposals: [{ frame: 0, boxes: [PROPOSAL] }],
    rules: [],
    required: [0, 1, 2],
    mode: "every-frame",
    draft: null,
  };
}

function makeServer() {
  const server = {
    hold: false, // when set, each save waits until the scenario answers it
    puts: [],
    async fetch(path, options = {}) {
      if (path === "/api/session") {
        return response(200, { reference: "synthetic", instances: [instance(1), instance(2)] });
      }
      const frame = path.match(/^\/api\/frames\/(\d+)\/(\d+)$/);
      if (frame) {
        const samples = new Uint16Array(ROWS * COLUMNS).fill(1000);
        return response(200, samples.buffer, { "X-Rows": ROWS, "X-Columns": COLUMNS, "X-Samples": 1, "X-Bits": 16 });
      }
      const draft = path.match(/^\/api\/drafts\/(\d+)$/);
      assert.ok(draft && options.method === "PUT", `unexpected request ${path}`);
      // Each save as sent; `answered` once the scenario has answered it.
      const put = { position: Number(draft[1]), body: JSON.parse(options.body), answered: false };
      server.puts.push(put);
      if (!server.hold) {
        put.answered = true;
        return response(200, {});
      }
      return new Promise((resolve) => {
        put.answer = (status = 200) => {
          put.answered = true;
          resolve(response(status, status === 200 ? {} : { error: "the save failed" }));
        };
      });
    },
    waiting() {
      return server.puts.filter((put) => !put.answered);
    },
  };
  return server;
}

// The page, loaded and started.

async function load(appPath, { hidden = false } = {}) {
  const document = makeDocument();
  if (hidden) document.visibilityState = "hidden";
  const clock = makeClock();
  const server = makeServer();
  const windowListeners = {};
  const window = {
    location: { hash: "#token", pathname: "/" },
    sessionStorage: { getItem: () => null, setItem: () => {} },
    history: { replaceState: () => {} },
    devicePixelRatio: 1,
    addEventListener: (type, listener) => (windowListeners[type] ||= []).push(listener),
  };
  const sandbox = {
    window,
    document,
    fetch: server.fetch,
    setTimeout: clock.setTimeout,
    clearTimeout: clock.clearTimeout,
    ImageData,
    HTMLInputElement,
    console,
  };
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(appPath, "utf8"), sandbox, { filename: appPath });
  await clock.advance(0);
  const $ = (id) => document.elements.get(id);
  const canvas = $("canvas");
  const scale = Math.min(CANVAS.width / COLUMNS, CANVAS.height / ROWS) * 0.98;
  const offset = { x: (CANVAS.width - COLUMNS * scale) / 2, y: (CANVAS.height - ROWS * scale) / 2 };
  const at = (row, column) => ({ clientX: offset.x + column * scale, clientY: offset.y + row * scale });
  const page = {
    $,
    clock,
    server,
    document,
    key: (key, extra = {}) =>
      document.dispatch("keydown", {
        key,
        shiftKey: false,
        ctrlKey: false,
        metaKey: false,
        altKey: false,
        target: canvas,
        ...extra,
      }),
    down: (row, column, button = 0) => canvas.dispatch("pointerdown", { pointerId: 1, button, ...at(row, column) }),
    move: (row, column) => canvas.dispatch("pointermove", { pointerId: 1, ...at(row, column) }),
    up: () => canvas.dispatch("pointerup", { pointerId: 1 }),
    // Down at one point, and moved to the other, without releasing.
    startDrawing(from, to) {
      page.down(...from);
      page.move(from[0] + (to[0] - from[0]) / 2, from[1] + (to[1] - from[1]) / 2);
      page.move(...to);
    },
    draw(from, to) {
      page.startDrawing(from, to);
      page.up();
    },
    // The screen point of a box's corner, as image row and column.
    corner: (box, which) => [[box[0], box[1]], [box[0], box[3]], [box[2], box[1]], [box[2], box[3]]][which],
    frameLabel: () => $("frame-label").textContent,
    instanceTitle: () => $("instance-title").textContent,
    toast: () => $("toast").textContent,
    saved: () => $("saved").textContent,
    beforeUnload: () => dispatchTo(windowListeners, "beforeunload", window, {}),
    setVisible(visible) {
      document.visibilityState = visible ? "visible" : "hidden";
      document.dispatch("visibilitychange");
    },
    // Shows every frame of the current instance, then returns to frame 0.
    async showEveryFrame() {
      for (let frame = 0; frame < FRAMES; frame += 1) {
        if (frame > 0) page.key("n");
        await clock.advance(400);
      }
      for (let frame = FRAMES - 1; frame > 0; frame -= 1) page.key("p");
      await clock.advance(400);
    },
    lastPut: (position) => {
      const puts = server.puts.filter((put) => put.position === position);
      return puts.length ? puts[puts.length - 1].body : null;
    },
  };
  return page;
}

const drawnOn = (draft) => (draft ? draft.drawn : []);

// The scenarios.

const SCENARIOS = {
  // A box begun on one frame never lands on another: the frame keys are
  // refused while drawing, and anything else that changes the frame
  // cancels the drawing.
  async "draw-then-change-frame"(page) {
    assert.equal(page.frameLabel(), "Frame 1 of 3 (index 0)");
    page.startDrawing([20.5, 10.5], [30.5, 40.5]);
    for (const key of ["n", "ArrowRight", "ArrowDown", "p", "N"]) {
      const event = page.key(key, { shiftKey: key === "N" });
      assert.ok(event.defaultPrevented);
      assert.equal(page.frameLabel(), "Frame 1 of 3 (index 0)", `${key} changed the frame while drawing`);
    }
    assert.match(page.toast(), /Release the region you are drawing/);
    page.up();
    await page.clock.advance(400);
    assert.deepEqual(drawnOn(page.lastPut(1)), [{ frame: 0, boxes: [[20, 10, 31, 41]] }]);

    // The scrubber is reached by another pointer: it changes the frame, so
    // the drawing is cancelled, and the release adds nothing anywhere.
    page.startDrawing([2.5, 30.5], [8.5, 50.5]);
    page.$("scrubber").dispatch("pointerdown", { pointerId: 2, clientX: 700, clientY: 10 });
    assert.equal(page.frameLabel(), "Frame 3 of 3 (index 2)");
    assert.match(page.toast(), /was cancelled, because the frame changed/);
    page.up();
    await page.clock.advance(400);
    assert.deepEqual(drawnOn(page.lastPut(1)), [{ frame: 0, boxes: [[20, 10, 31, 41]] }]);
  },

  // Changing instance while drawing, from the keys or the queue, cannot
  // move the box to another instance, and confirming waits for the
  // drawing to end.
  async "draw-then-change-instance"(page) {
    await page.showEveryFrame();
    page.key("Enter");
    await page.clock.advance(400);
    assert.equal(page.lastPut(1).redaction, "accepted");
    assert.equal(page.instanceTitle(), "Instance 2");
    page.key("k");
    await page.clock.advance(400);
    assert.equal(page.instanceTitle(), "Instance 1");

    page.startDrawing([20.5, 10.5], [30.5, 40.5]);
    page.key("j");
    assert.equal(page.instanceTitle(), "Instance 1", "J changed the instance while drawing");
    page.key("Enter");
    assert.equal(page.lastPut(1).redaction, "accepted");
    page.$("confirm-button").dispatch("click");
    assert.match(page.toast(), /before giving a verdict/);
    page.up();
    await page.clock.advance(400);
    // The box is on the instance it was drawn on, whose acceptance it cleared.
    assert.equal(page.lastPut(1).redaction, null);
    assert.deepEqual(drawnOn(page.lastPut(1)), [{ frame: 0, boxes: [[20, 10, 31, 41]] }]);
    assert.deepEqual(drawnOn(page.lastPut(2)), []);

    // A click in the queue, from another pointer, cancels the drawing.
    page.startDrawing([2.5, 30.5], [8.5, 50.5]);
    page.$("instances").children[1].dispatch("click");
    assert.equal(page.instanceTitle(), "Instance 2");
    page.up();
    await page.clock.advance(400);
    assert.deepEqual(drawnOn(page.lastPut(1)), [{ frame: 0, boxes: [[20, 10, 31, 41]] }]);
    assert.deepEqual(drawnOn(page.lastPut(2)), []);
  },

  // Resizing a box is bound the same way, and Escape cancels it.
  async "resize-then-change-frame"(page) {
    page.draw([20.5, 10.5], [30.5, 40.5]);
    await page.clock.advance(400);
    const box = [20, 10, 31, 41];
    assert.deepEqual(drawnOn(page.lastPut(1)), [{ frame: 0, boxes: [box] }]);
    // The new box is selected, so its corners are handles.
    page.down(...page.corner(box, 3));
    page.move(35.5, 50.5);
    page.key("n");
    assert.equal(page.frameLabel(), "Frame 1 of 3 (index 0)");
    page.key("Escape");
    page.up();
    await page.clock.advance(400);
    assert.deepEqual(drawnOn(page.lastPut(1)), [{ frame: 0, boxes: [box] }]);
    // Without Escape, the resize finishes on the frame where it began.
    page.down(...page.corner(box, 3));
    page.move(35.5, 50.5);
    page.key("n");
    page.up();
    await page.clock.advance(400);
    assert.equal(page.frameLabel(), "Frame 1 of 3 (index 0)");
    assert.deepEqual(drawnOn(page.lastPut(1)), [{ frame: 0, boxes: [[20, 10, 36, 51]] }]);
  },

  // "All work saved" appears only once the server has confirmed the latest
  // revision of every instance: not when an older save completes, not
  // while a newer one waits or is in flight, and not while another
  // instance's save has failed.
  async "save-indicator"(page) {
    await page.showEveryFrame();
    page.server.hold = true;
    page.key("Enter");
    await page.clock.advance(400);
    const accepted = page.server.waiting();
    assert.equal(accepted.length, 1);
    assert.equal(accepted[0].body.redaction, "accepted");
    assert.equal(page.saved(), "Saving");

    // Instance 2 opened: its first frame's display is saved too.
    await page.clock.advance(400);
    const seenOnTwo = page.server.waiting().filter((put) => put.position === 2);
    assert.equal(seenOnTwo.length, 1);

    // Back to instance 1, which is corrected and confirmed again while the
    // acceptance is still in flight.
    page.key("k");
    page.draw([20.5, 10.5], [30.5, 40.5]);
    page.key("Enter");
    // Only one request at a time goes to each instance.
    assert.equal(page.server.waiting().filter((put) => put.position === 1).length, 1);
    accepted[0].answer();
    await page.clock.settle();
    assert.equal(page.saved(), "Saving", "an older save completing reported the newer work saved");
    await page.clock.advance(400);
    const revised = page.server.waiting().filter((put) => put.position === 1);
    assert.equal(revised.length, 1);
    assert.equal(revised[0].body.redaction, "revised");
    assert.deepEqual(revised[0].body.drawn, [{ frame: 0, boxes: [[20, 10, 31, 41]] }]);
    assert.equal(page.beforeUnload().defaultPrevented, true);
    seenOnTwo[0].answer();
    await page.clock.settle();
    assert.equal(page.saved(), "Saving");
    revised[0].answer();
    await page.clock.settle();
    assert.equal(page.saved(), "All work saved");
    assert.equal(page.beforeUnload().defaultPrevented, false);

    // A failed save stays reported after another instance's save succeeds.
    page.key("j");
    page.key("k");
    page.draw([2.5, 30.5], [8.5, 50.5]);
    await page.clock.advance(400);
    const failing = page.server.waiting();
    assert.equal(failing.length, 1);
    failing[0].answer(500);
    await page.clock.settle();
    assert.equal(page.saved(), "Not saved: 1 instance(s)");
    page.key("j");
    page.key("r");
    await page.clock.advance(400);
    const rejected = page.server.waiting();
    assert.equal(rejected.length, 1);
    assert.equal(rejected[0].position, 2);
    rejected[0].answer();
    await page.clock.settle();
    assert.equal(page.saved(), "Not saved: 1 instance(s)");
    assert.equal(page.beforeUnload().defaultPrevented, true);

    // Opening the summary retries it, and says when the app can stop.
    page.key("s");
    await page.clock.settle();
    assert.match(page.$("summary-saved").textContent, /Saving your latest changes/);
    const retry = page.server.waiting();
    assert.equal(retry.length, 1);
    assert.equal(retry[0].position, 1);
    assert.equal(retry[0].body.drawn[0].boxes.length, 2);
    retry[0].answer();
    await page.clock.settle();
    assert.equal(page.saved(), "All work saved");
    assert.equal(page.$("summary-saved").textContent, "All your work is saved.");
  },

  // A frame counts as shown only after SEEN_AFTER_MS with the page visible
  // and no dialog over it, and the time starts again after either.
  async "shown-only-when-visible"(page) {
    const seen = () => page.$("seen-label").textContent;
    await page.clock.advance(1000);
    assert.equal(seen(), "every frame required; 0 of 3 shown", "a frame loaded in a hidden page counted as shown");
    assert.equal(page.server.puts.length, 0);
    page.setVisible(true);
    await page.clock.advance(299);
    assert.equal(seen(), "every frame required; 0 of 3 shown");
    await page.clock.advance(2);
    assert.equal(seen(), "every frame required; 1 of 3 shown");

    page.key("n");
    await page.clock.advance(200);
    page.setVisible(false);
    await page.clock.advance(1000);
    page.setVisible(true);
    await page.clock.advance(200);
    assert.equal(seen(), "every frame required; 1 of 3 shown", "time hidden counted towards showing");
    await page.clock.advance(101);
    assert.equal(seen(), "every frame required; 2 of 3 shown");

    page.key("n");
    await page.clock.advance(200);
    page.key("?");
    await page.clock.advance(1000);
    assert.equal(seen(), "every frame required; 2 of 3 shown", "time under a dialog counted towards showing");
    page.key("?");
    await page.clock.advance(299);
    assert.equal(seen(), "every frame required; 2 of 3 shown");
    await page.clock.advance(2);
    assert.equal(seen(), "every frame required; all shown");
    await page.clock.advance(400);
    assert.deepEqual(page.lastPut(1).seen, [0, 1, 2]);
  },
};

async function main() {
  const [appPath, scenario] = process.argv.slice(2);
  assert.ok(scenario in SCENARIOS, `no scenario ${scenario}`);
  const page = await load(appPath, { hidden: scenario === "shown-only-when-visible" });
  await SCENARIOS[scenario](page);
  process.stdout.write(`${scenario}: passed\n`);
}

main().catch((error) => {
  process.stderr.write(`${error.stack || error}\n`);
  process.exit(1);
});
