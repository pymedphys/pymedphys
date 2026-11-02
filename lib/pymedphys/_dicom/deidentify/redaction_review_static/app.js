// Copyright (C) 2026 Matthew Jennings
// Licensed under the Apache License, Version 2.0; see redaction_review_app.py.
//
// The redaction review app's page. The server is the authority: it
// checks every draft against the QC pack before saving it, and the
// attestation checks the saved verdicts again. This script only shows the
// pack's frames and collects the reviewer's work.
"use strict";

(() => {
  const TOKEN_HEADER = "X-Review-Token";
  const SEEN_AFTER_MS = 300;
  const SAVE_AFTER_MS = 300;
  const PREFETCH = 3;
  const CACHE_FRAMES = 48;
  const HANDLE_PX = 7;
  const COLOURS = {
    proposal: "#ff00ff",
    dropped: "#9e9e9e",
    drawn: "#00e5ff",
    rule: "#ffd600",
    selected: "#ffffff",
  };
  const WINDOWS = ["percentile", "full range", "inverted"];

  // The token travels after the "#", which the browser never sends to a
  // server; it is kept for this tab only and taken out of the address bar.
  let token = window.location.hash.slice(1);
  if (token) {
    window.sessionStorage.setItem("review-token", token);
    window.history.replaceState(null, "", window.location.pathname);
  } else {
    token = window.sessionStorage.getItem("review-token") || "";
  }

  const $ = (id) => document.getElementById(id);
  const canvas = $("canvas");
  const context = canvas.getContext("2d");
  const scrubber = $("scrubber");
  const scrubberContext = scrubber.getContext("2d");

  const state = {
    reference: "",
    instances: [],
    work: new Map(), // position -> working draft
    current: 0, // index into instances
    frame: 0,
    view: { scale: 1, x: 0, y: 0, fitted: true },
    window: { preset: 0, low: 0, high: 65535 },
    blackout: false,
    selected: null, // index into this frame's drawn boxes
    drag: null,
    space: false,
    cache: new Map(), // "position/frame" -> frame data, least recent first
    loading: new Map(),
    image: null, // the current frame's rendered bitmap
    seenTimer: null,
    saveTimers: new Map(),
  };

  // Talking to the server.

  async function api(path, options = {}) {
    const response = await fetch(path, {
      ...options,
      headers: { ...(options.headers || {}), [TOKEN_HEADER]: token },
      cache: "no-store",
      credentials: "omit",
    });
    if (!response.ok) {
      let message = `the server refused the request (${response.status})`;
      try {
        message = (await response.json()).error || message;
      } catch (error) {
        // The status says enough.
      }
      throw new Error(message);
    }
    return response;
  }

  async function loadFrame(position, index) {
    const key = `${position}/${index}`;
    if (state.cache.has(key)) {
      const found = state.cache.get(key);
      state.cache.delete(key);
      state.cache.set(key, found);
      return found;
    }
    if (state.loading.has(key)) return state.loading.get(key);
    const pending = (async () => {
      const response = await api(`/api/frames/${position}/${index}`);
      const rows = Number(response.headers.get("X-Rows"));
      const columns = Number(response.headers.get("X-Columns"));
      const samples = Number(response.headers.get("X-Samples"));
      const bits = Number(response.headers.get("X-Bits"));
      const buffer = await response.arrayBuffer();
      const data = bits === 16 ? new Uint16Array(buffer) : new Uint8Array(buffer);
      if (data.length !== rows * columns * samples) {
        throw new Error("a frame arrived with the wrong number of samples");
      }
      const frame = { rows, columns, samples, bits, data, percentile: null };
      state.cache.set(key, frame);
      while (state.cache.size > CACHE_FRAMES) {
        state.cache.delete(state.cache.keys().next().value);
      }
      return frame;
    })();
    state.loading.set(key, pending);
    try {
      return await pending;
    } finally {
      state.loading.delete(key);
    }
  }

  // The reviewer's work on each instance, as the server saves it.

  const boxKey = (box) => box.join(",");
  const sortBoxes = (boxes) =>
    boxes.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3]);

  function workFrom(instance) {
    const draft = instance.draft;
    const work = {
      redaction: draft ? draft.redaction : null,
      drawn: new Map(),
      dropped: new Map(),
      seen: new Set(draft ? draft.seen : []),
      undo: [],
      redo: [],
    };
    if (draft) {
      for (const { frame, boxes } of draft.drawn) work.drawn.set(frame, boxes.map((b) => b.slice()));
      for (const { frame, boxes } of draft.dropped) work.dropped.set(frame, new Set(boxes.map(boxKey)));
    }
    return work;
  }

  function draftDocument(work) {
    const regions = (map, toList) =>
      [...map.keys()]
        .sort((a, b) => a - b)
        .map((frame) => ({ frame, boxes: sortBoxes(toList(map.get(frame))) }))
        .filter((entry) => entry.boxes.length > 0);
    // Identical boxes drawn twice are one region.
    const unique = (boxes) => [...new Map(boxes.map((b) => [boxKey(b), b])).values()];
    return {
      redaction: work.redaction,
      drawn: regions(work.drawn, unique),
      dropped: regions(work.dropped, (keys) => [...keys].map((k) => k.split(",").map(Number))),
      seen: [...work.seen].sort((a, b) => a - b),
    };
  }

  function snapshot(work) {
    return JSON.stringify({
      redaction: work.redaction,
      drawn: [...work.drawn.entries()],
      dropped: [...work.dropped.entries()].map(([f, s]) => [f, [...s]]),
    });
  }

  function restore(work, text) {
    const saved = JSON.parse(text);
    work.redaction = saved.redaction;
    work.drawn = new Map(saved.drawn);
    work.dropped = new Map(saved.dropped.map(([f, s]) => [f, new Set(s)]));
  }

  // Every change to regions goes through here: it can be undone, and it
  // clears a verdict already given, which no longer describes the regions.
  function change(mutate) {
    const work = currentWork();
    work.undo.push(snapshot(work));
    work.redo = [];
    mutate(work);
    if (work.redaction !== null) {
      work.redaction = null;
      toast("The regions changed, so the instance's verdict was cleared.");
    }
    save(currentInstance().position);
    render();
  }

  function save(position) {
    clearTimeout(state.saveTimers.get(position));
    $("saved").textContent = "Saving";
    state.saveTimers.set(
      position,
      setTimeout(async () => {
        try {
          await api(`/api/drafts/${position}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(draftDocument(state.work.get(position))),
          });
          $("saved").textContent = "All work saved";
        } catch (error) {
          $("saved").textContent = "Not saved";
          toast(error.message, true);
        }
      }, SAVE_AFTER_MS),
    );
  }

  const currentInstance = () => state.instances[state.current];
  const currentWork = () => state.work.get(currentInstance().position);

  function proposalsOf(instance, frame) {
    const entry = instance.proposals.find((p) => p.frame === frame);
    return entry ? entry.boxes : [];
  }

  function isRule(instance, box) {
    return instance.rules.some((rule) => boxKey(rule) === boxKey(box));
  }

  function flaggedFrames(instance) {
    return instance.proposals.map((p) => p.frame);
  }

  function missingFrames(instance, work) {
    return instance.required.filter((frame) => !work.seen.has(frame));
  }

  function changed(work) {
    const any = (map) => [...map.values()].some((v) => (v.size ?? v.length) > 0);
    return any(work.drawn) || any(work.dropped);
  }

  // Drawing.

  function resize() {
    const ratio = window.devicePixelRatio || 1;
    const { width, height } = canvas.getBoundingClientRect();
    canvas.width = Math.max(1, Math.round(width * ratio));
    canvas.height = Math.max(1, Math.round(height * ratio));
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const bar = scrubber.getBoundingClientRect();
    scrubber.width = Math.max(1, Math.round(bar.width * ratio));
    scrubber.height = Math.max(1, Math.round(bar.height * ratio));
    scrubberContext.setTransform(ratio, 0, 0, ratio, 0, 0);
    if (state.view.fitted) fit();
    render();
  }

  function fit() {
    const instance = currentInstance();
    if (!instance) return;
    const { width, height } = canvas.getBoundingClientRect();
    const scale = Math.min(width / instance.columns, height / instance.rows) * 0.98;
    state.view = {
      scale,
      x: (width - instance.columns * scale) / 2,
      y: (height - instance.rows * scale) / 2,
      fitted: true,
    };
  }

  function percentile(frame) {
    if (frame.percentile) return frame.percentile;
    // A histogram of the frame's samples, padding (0) left out.
    const counts = new Uint32Array(65536);
    let total = 0;
    for (const value of frame.data) {
      if (value > 0) {
        counts[value] += 1;
        total += 1;
      }
    }
    const find = (fraction) => {
      let running = 0;
      const target = fraction * total;
      for (let value = 1; value < 65536; value += 1) {
        running += counts[value];
        if (running >= target) return value;
      }
      return 65535;
    };
    let low = find(0.005);
    let high = find(0.995);
    if (high <= low) high = low + 1;
    frame.percentile = [low, high];
    return frame.percentile;
  }

  function applyPreset(frame) {
    const preset = WINDOWS[state.window.preset];
    if (preset === "percentile" && frame && frame.bits === 16) {
      [state.window.low, state.window.high] = percentile(frame);
    } else if (preset === "inverted") {
      [state.window.low, state.window.high] = [65535, 1];
    } else {
      [state.window.low, state.window.high] = [1, 65535];
    }
    $("window-button").textContent = `Window: ${preset}`;
  }

  function bitmapOf(frame, instance, work) {
    const pixels = new ImageData(frame.columns, frame.rows);
    const out = pixels.data;
    if (frame.bits === 16) {
      const lut = new Uint8ClampedArray(65536);
      const { low, high } = state.window;
      const span = high - low || 1;
      for (let value = 1; value < 65536; value += 1) {
        lut[value] = ((value - low) / span) * 255;
      }
      lut[0] = 0; // padding is black, as in the pack's previews
      const data = frame.data;
      for (let i = 0, j = 0; i < data.length; i += 1, j += 4) {
        const grey = lut[data[i]];
        out[j] = grey;
        out[j + 1] = grey;
        out[j + 2] = grey;
        out[j + 3] = 255;
      }
    } else {
      const data = frame.data;
      for (let i = 0, j = 0; i < data.length; i += 3, j += 4) {
        out[j] = data[i];
        out[j + 1] = data[i + 1];
        out[j + 2] = data[i + 2];
        out[j + 3] = 255;
      }
    }
    if (state.blackout) {
      // As the run given the verdict writes it: each region kept or drawn
      // set to the fill, which shows black whatever the photometric
      // interpretation, since the review frame is brightest last.
      for (const box of blackedOut(instance, work, state.frame)) {
        for (let row = box[0]; row < box[2]; row += 1) {
          out.fill(0, (row * frame.columns + box[1]) * 4, (row * frame.columns + box[3]) * 4);
          for (let column = box[1]; column < box[3]; column += 1) {
            out[(row * frame.columns + column) * 4 + 3] = 255;
          }
        }
      }
    }
    const offscreen = document.createElement("canvas");
    offscreen.width = frame.columns;
    offscreen.height = frame.rows;
    offscreen.getContext("2d").putImageData(pixels, 0, 0);
    return offscreen;
  }

  function blackedOut(instance, work, frame) {
    const dropped = work.dropped.get(frame) || new Set();
    return [
      ...proposalsOf(instance, frame).filter((box) => !dropped.has(boxKey(box))),
      ...(work.drawn.get(frame) || []),
    ];
  }

  async function show() {
    const instance = currentInstance();
    const frameIndex = state.frame;
    clearTimeout(state.seenTimer);
    $("loading").classList.remove("hidden");
    let frame;
    try {
      frame = await loadFrame(instance.position, frameIndex);
    } catch (error) {
      toast(error.message, true);
      return;
    } finally {
      $("loading").classList.add("hidden");
    }
    if (currentInstance() !== instance || state.frame !== frameIndex) return;
    if (WINDOWS[state.window.preset] === "percentile") applyPreset(frame);
    state.image = { key: `${instance.position}/${frameIndex}`, frame };
    render();
    for (let ahead = 1; ahead <= PREFETCH; ahead += 1) {
      if (frameIndex + ahead < instance.frames) {
        loadFrame(instance.position, frameIndex + ahead).catch(() => {});
      }
    }
  }

  function render() {
    const instance = currentInstance();
    if (!instance) return;
    const work = currentWork();
    const { width, height } = canvas.getBoundingClientRect();
    context.fillStyle = "#000";
    context.fillRect(0, 0, width, height);
    const key = `${instance.position}/${state.frame}`;
    if (state.image && state.image.key === key) {
      const bitmap = bitmapOf(state.image.frame, instance, work);
      context.imageSmoothingEnabled = false;
      const { scale, x, y } = state.view;
      context.drawImage(bitmap, x, y, instance.columns * scale, instance.rows * scale);
      drawRegions(instance, work);
      watchSeen(instance, work);
    }
    drawScrubber(instance, work);
    renderPanel(instance, work);
    renderLabels(instance, work);
    renderQueue();
  }

  function toScreen(box) {
    const { scale, x, y } = state.view;
    return [x + box[1] * scale, y + box[0] * scale, (box[3] - box[1]) * scale, (box[2] - box[0]) * scale];
  }

  function strokeBox(box, colour, dash, width) {
    const [left, top, w, h] = toScreen(box);
    context.save();
    context.strokeStyle = colour;
    context.lineWidth = width;
    context.setLineDash(dash);
    context.strokeRect(left + width / 2, top + width / 2, Math.max(0, w - width), Math.max(0, h - width));
    context.restore();
  }

  function drawRegions(instance, work) {
    const dropped = work.dropped.get(state.frame) || new Set();
    for (const box of proposalsOf(instance, state.frame)) {
      if (isRule(instance, box)) strokeBox(box, COLOURS.rule, [2, 3], 2);
      else if (dropped.has(boxKey(box))) strokeBox(box, COLOURS.dropped, [6, 4], 1.5);
      else strokeBox(box, COLOURS.proposal, [], 2);
    }
    const drawn = work.drawn.get(state.frame) || [];
    drawn.forEach((box, index) => {
      const selected = index === state.selected;
      strokeBox(box, selected ? COLOURS.selected : COLOURS.drawn, [], selected ? 3 : 2.5);
      if (selected) {
        for (const [cx, cy] of corners(box)) {
          context.fillStyle = COLOURS.drawn;
          context.fillRect(cx - HANDLE_PX / 2, cy - HANDLE_PX / 2, HANDLE_PX, HANDLE_PX);
        }
      }
    });
    if (state.drag && state.drag.kind === "draw" && state.drag.box) {
      strokeBox(state.drag.box, COLOURS.drawn, [4, 2], 2);
    }
  }

  function corners(box) {
    const [left, top, w, h] = toScreen(box);
    return [
      [left, top],
      [left + w, top],
      [left, top + h],
      [left + w, top + h],
    ];
  }

  // A frame counts as shown once the whole of it has been on screen, drawn,
  // for SEEN_AFTER_MS.
  function watchSeen(instance, work) {
    if (work.seen.has(state.frame)) return;
    const { width, height } = canvas.getBoundingClientRect();
    const [left, top, w, h] = toScreen([0, 0, instance.rows, instance.columns]);
    const whole = left >= -0.5 && top >= -0.5 && left + w <= width + 0.5 && top + h <= height + 0.5;
    clearTimeout(state.seenTimer);
    if (!whole) return;
    const frame = state.frame;
    state.seenTimer = setTimeout(() => {
      if (currentInstance() !== instance || state.frame !== frame) return;
      work.seen.add(frame);
      save(instance.position);
      render();
    }, SEEN_AFTER_MS);
  }

  function drawScrubber(instance, work) {
    const { width, height } = scrubber.getBoundingClientRect();
    scrubberContext.fillStyle = "#000";
    scrubberContext.fillRect(0, 0, width, height);
    const step = width / instance.frames;
    const flagged = new Set(flaggedFrames(instance));
    for (let frame = 0; frame < instance.frames; frame += 1) {
      const x = frame * step;
      scrubberContext.fillStyle = work.seen.has(frame) ? "#2e5e3a" : "#3c4043";
      scrubberContext.fillRect(x, 8, Math.max(1, step - (step > 3 ? 1 : 0)), height - 8);
      if (flagged.has(frame)) {
        scrubberContext.fillStyle = COLOURS.proposal;
        scrubberContext.fillRect(x, 0, Math.max(1, step - (step > 3 ? 1 : 0)), 6);
      }
    }
    scrubberContext.strokeStyle = "#ffffff";
    scrubberContext.lineWidth = 2;
    scrubberContext.strokeRect(state.frame * step + 1, 1, Math.max(2, step - 2), height - 2);
  }

  function renderLabels(instance, work) {
    const missing = missingFrames(instance, work);
    $("instance-title").textContent = `Instance ${instance.position}`;
    // Counted from 1 here, and by index from 0, as the pack and the
    // attestation's summary give it.
    $("frame-label").textContent = `Frame ${state.frame + 1} of ${instance.frames} (index ${state.frame})`;
    const scope = instance.mode === "flagged-frames" ? "flagged frames required" : "every frame required";
    $("seen-label").textContent =
      missing.length === 0
        ? `${scope}; all shown`
        : `${scope}; ${instance.required.length - missing.length} of ${instance.required.length} shown`;
    const words = {
      accepted: "Confirmed: the finder's regions, as proposed",
      revised: "Confirmed: your regions",
      rejected: "Rejected: it will not be released",
    };
    $("verdict-label").textContent = work.redaction ? words[work.redaction] : "No verdict yet";
    $("confirm-button").disabled = missing.length > 0;
    $("confirm-button").title =
      missing.length > 0
        ? `Show every frame first: ${missing.length} still to show (Shift+N or N)`
        : "Confirm the regions (Enter)";
    $("blackout-button").setAttribute("aria-pressed", String(state.blackout));
    const decided = state.instances.filter((i) => state.work.get(i.position).redaction).length;
    $("progress").textContent = `${decided} of ${state.instances.length} instances decided`;
  }

  function renderPanel(instance, work) {
    const list = $("regions");
    list.replaceChildren();
    const dropped = work.dropped.get(state.frame) || new Set();
    const add = (box, kind, onClick) => {
      const item = document.createElement("li");
      const swatch = document.createElement("span");
      swatch.className = `swatch ${kind === "kept" ? "proposal" : kind}`;
      item.append(swatch, document.createTextNode(`[${box.join(", ")}]`));
      if (kind === "dropped") item.classList.add("dropped");
      if (onClick) item.addEventListener("click", onClick);
      list.append(item);
      return item;
    };
    for (const box of proposalsOf(instance, state.frame)) {
      if (isRule(instance, box)) add(box, "rule");
      else add(box, dropped.has(boxKey(box)) ? "dropped" : "kept", () => toggleProposal(box));
    }
    (work.drawn.get(state.frame) || []).forEach((box, index) => {
      const item = add(box, "drawn", () => {
        state.selected = index;
        render();
      });
      if (index === state.selected) item.classList.add("selected");
    });
    if (!list.children.length) {
      const item = document.createElement("li");
      item.className = "muted";
      item.textContent = "None. Drag on the frame to draw one.";
      list.append(item);
    }
  }

  function renderQueue() {
    const list = $("instances");
    const undecidedOnly = $("undecided-only").checked;
    list.replaceChildren();
    state.instances.forEach((instance, index) => {
      const work = state.work.get(instance.position);
      if (undecidedOnly && work.redaction && index !== state.current) return;
      const item = document.createElement("li");
      if (index === state.current) item.classList.add("current");
      const title = document.createElement("span");
      title.textContent = `Instance ${instance.position}`;
      const chip = document.createElement("span");
      const status = work.redaction || (work.seen.size || changed(work) ? "working" : "to review");
      chip.className = `chip ${work.redaction || (status === "working" ? "working" : "")}`;
      chip.textContent = status;
      const detail = document.createElement("span");
      detail.className = "detail";
      const shown = instance.required.length - missingFrames(instance, work).length;
      detail.textContent = `${instance.frames} frame(s), ${flaggedFrames(instance).length} flagged, ${shown}/${instance.required.length} shown`;
      item.append(title, chip, detail);
      item.addEventListener("click", () => open(index, 0));
      list.append(item);
    });
  }

  // Actions.

  function open(index, frame) {
    if (index < 0 || index >= state.instances.length) return;
    const instanceChanged = index !== state.current;
    state.current = index;
    state.frame = Math.max(0, Math.min(frame, currentInstance().frames - 1));
    state.selected = null;
    if (instanceChanged || state.view.fitted) fit();
    render();
    show();
  }

  function goFrame(frame) {
    open(state.current, frame);
  }

  function nextFlagged(direction) {
    const instance = currentInstance();
    const flagged = flaggedFrames(instance);
    const found =
      direction > 0 ? flagged.find((f) => f > state.frame) : [...flagged].reverse().find((f) => f < state.frame);
    if (found === undefined) toast("No further frame with a finder's region in this instance.");
    else goFrame(found);
  }

  function toggleProposal(box) {
    const instance = currentInstance();
    if (isRule(instance, box)) {
      toast("A region rule's region cannot be dropped here; rules change only through their store.");
      return;
    }
    change((work) => {
      const dropped = work.dropped.get(state.frame) || new Set();
      if (dropped.has(boxKey(box))) dropped.delete(boxKey(box));
      else dropped.add(boxKey(box));
      work.dropped.set(state.frame, dropped);
    });
  }

  function dropAllHere() {
    const instance = currentInstance();
    const droppable = proposalsOf(instance, state.frame).filter((box) => !isRule(instance, box));
    if (!droppable.length) return;
    change((work) => work.dropped.set(state.frame, new Set(droppable.map(boxKey))));
  }

  function removeSelected() {
    if (state.selected === null) return;
    const index = state.selected;
    state.selected = null;
    change((work) => {
      const drawn = (work.drawn.get(state.frame) || []).slice();
      drawn.splice(index, 1);
      work.drawn.set(state.frame, drawn);
    });
  }

  function undo(redo) {
    const work = currentWork();
    const from = redo ? work.redo : work.undo;
    const to = redo ? work.undo : work.redo;
    if (!from.length) return;
    to.push(snapshot(work));
    restore(work, from.pop());
    state.selected = null;
    save(currentInstance().position);
    render();
  }

  function decide(redaction) {
    const instance = currentInstance();
    const work = currentWork();
    if (redaction !== "rejected" && redaction !== null) {
      const missing = missingFrames(instance, work);
      if (missing.length) {
        toast(`Show every frame before confirming: ${missing.length} still to show.`, true);
        return;
      }
      redaction = changed(work) ? "revised" : "accepted";
    }
    work.undo.push(snapshot(work));
    work.redo = [];
    work.redaction = redaction;
    save(instance.position);
    render();
    if (redaction) {
      const next = state.instances.findIndex((i, index) => index > state.current && !state.work.get(i.position).redaction);
      if (next >= 0) open(next, 0);
      else toast("That was the last instance without a verdict. Open the summary (S) to check your work.");
    }
  }

  function zoomAt(factor, sx, sy) {
    const view = state.view;
    const scale = Math.min(64, Math.max(0.02, view.scale * factor));
    const ratio = scale / view.scale;
    state.view = { scale, x: sx - (sx - view.x) * ratio, y: sy - (sy - view.y) * ratio, fitted: false };
    render();
  }

  // Pointer handling.

  function imagePoint(event) {
    const rect = canvas.getBoundingClientRect();
    const sx = event.clientX - rect.left;
    const sy = event.clientY - rect.top;
    const { scale, x, y } = state.view;
    return { sx, sy, row: (sy - y) / scale, column: (sx - x) / scale };
  }

  function clampBox(a, b, instance) {
    const clamp = (value, most) => Math.max(0, Math.min(most, value));
    const top = clamp(Math.floor(Math.min(a.row, b.row)), instance.rows);
    const left = clamp(Math.floor(Math.min(a.column, b.column)), instance.columns);
    const bottom = clamp(Math.ceil(Math.max(a.row, b.row)), instance.rows);
    const right = clamp(Math.ceil(Math.max(a.column, b.column)), instance.columns);
    return [top, left, bottom, right];
  }

  function hit(point) {
    const instance = currentInstance();
    const work = currentWork();
    const drawn = work.drawn.get(state.frame) || [];
    if (state.selected !== null && drawn[state.selected]) {
      const found = corners(drawn[state.selected]).findIndex(
        ([cx, cy]) => Math.abs(cx - point.sx) <= HANDLE_PX && Math.abs(cy - point.sy) <= HANDLE_PX,
      );
      if (found >= 0) return { kind: "handle", index: state.selected, corner: found };
    }
    const inside = (box) =>
      point.row >= box[0] && point.row < box[2] && point.column >= box[1] && point.column < box[3];
    // The smallest box under the point wins, so a box inside another can be reached.
    const area = (box) => (box[2] - box[0]) * (box[3] - box[1]);
    const drawnHit = drawn
      .map((box, index) => ({ box, index }))
      .filter(({ box }) => inside(box))
      .sort((a, b) => area(a.box) - area(b.box))[0];
    if (drawnHit) return { kind: "drawn", index: drawnHit.index };
    const proposal = proposalsOf(instance, state.frame)
      .filter(inside)
      .sort((a, b) => area(a) - area(b))[0];
    if (proposal) return { kind: "proposal", box: proposal };
    return null;
  }

  canvas.addEventListener("contextmenu", (event) => event.preventDefault());

  canvas.addEventListener("pointerdown", (event) => {
    canvas.focus();
    canvas.setPointerCapture(event.pointerId);
    const point = imagePoint(event);
    if (event.button === 1 || (event.button === 0 && state.space)) {
      state.drag = { kind: "pan", start: point, view: { ...state.view } };
      canvas.classList.add("panning");
      return;
    }
    if (event.button === 2) {
      state.drag = { kind: "window", start: point, window: { ...state.window } };
      return;
    }
    if (event.button !== 0 || !state.image) return;
    const target = hit(point);
    if (target && target.kind === "handle") {
      const box = currentWork().drawn.get(state.frame)[target.index];
      const opposite = corners(box)[3 - target.corner];
      const { scale, x, y } = state.view;
      state.drag = {
        kind: "draw",
        resize: target.index,
        start: { row: (opposite[1] - y) / scale, column: (opposite[0] - x) / scale },
        moved: true,
        box,
      };
      return;
    }
    state.drag = { kind: "draw", start: point, target, moved: false, box: null };
  });

  canvas.addEventListener("pointermove", (event) => {
    const drag = state.drag;
    if (!drag) return;
    const point = imagePoint(event);
    if (drag.kind === "pan") {
      state.view = {
        ...drag.view,
        x: drag.view.x + point.sx - drag.start.sx,
        y: drag.view.y + point.sy - drag.start.sy,
        fitted: false,
      };
      render();
    } else if (drag.kind === "window") {
      const width = Math.max(2, drag.window.high - drag.window.low + (point.sx - drag.start.sx) * 64);
      const level = (drag.window.high + drag.window.low) / 2 - (point.sy - drag.start.sy) * 64;
      state.window = { preset: state.window.preset, low: level - width / 2, high: level + width / 2 };
      $("window-button").textContent = "Window: custom";
      render();
    } else if (drag.kind === "draw") {
      if (!drag.moved && Math.hypot(point.sx - drag.start.sx, point.sy - drag.start.sy) < 4) return;
      drag.moved = true;
      drag.box = clampBox(drag.start, point, currentInstance());
      render();
    }
  });

  canvas.addEventListener("pointerup", () => {
    const drag = state.drag;
    state.drag = null;
    canvas.classList.remove("panning");
    if (!drag || drag.kind !== "draw") return;
    if (!drag.moved) {
      // A click: on a finder's region, drop or keep it; on one of yours,
      // select it; elsewhere, clear the selection.
      if (drag.target && drag.target.kind === "proposal") toggleProposal(drag.target.box);
      else {
        state.selected = drag.target && drag.target.kind === "drawn" ? drag.target.index : null;
        render();
      }
      return;
    }
    const box = drag.box;
    if (!box || box[2] - box[0] < 1 || box[3] - box[1] < 1) {
      render();
      return;
    }
    change((work) => {
      const drawn = (work.drawn.get(state.frame) || []).slice();
      if (drag.resize !== undefined) drawn[drag.resize] = box;
      else drawn.push(box);
      work.drawn.set(state.frame, drawn);
      state.selected = drag.resize !== undefined ? drag.resize : drawn.length - 1;
    });
  });

  canvas.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      const point = imagePoint(event);
      zoomAt(Math.exp(-event.deltaY * 0.0015), point.sx, point.sy);
    },
    { passive: false },
  );

  function scrubTo(event) {
    const rect = scrubber.getBoundingClientRect();
    const instance = currentInstance();
    goFrame(Math.floor(((event.clientX - rect.left) / rect.width) * instance.frames));
  }
  scrubber.addEventListener("pointerdown", (event) => {
    scrubber.setPointerCapture(event.pointerId);
    scrubTo(event);
  });
  scrubber.addEventListener("pointermove", (event) => {
    if (event.buttons & 1) scrubTo(event);
  });

  // Keys.

  document.addEventListener("keydown", (event) => {
    if (document.querySelector("dialog[open]")) {
      if (event.key === "Escape") return;
      if (event.key === "?" || event.key.toLowerCase() === "s") {
        document.querySelector("dialog[open]").close();
        event.preventDefault();
      }
      return;
    }
    if (event.target instanceof HTMLInputElement) return;
    const key = event.key;
    const lower = key.toLowerCase();
    if (key === " ") {
      state.space = true;
      event.preventDefault();
      return;
    }
    const actions = {
      n: () => (event.shiftKey ? nextFlagged(1) : goFrame(state.frame + 1)),
      arrowright: () => goFrame(state.frame + 1),
      arrowdown: () => goFrame(state.frame + 1),
      p: () => (event.shiftKey ? nextFlagged(-1) : goFrame(state.frame - 1)),
      arrowleft: () => goFrame(state.frame - 1),
      arrowup: () => goFrame(state.frame - 1),
      j: () => open(state.current + 1, 0),
      k: () => open(state.current - 1, 0),
      c: dropAllHere,
      delete: removeSelected,
      backspace: removeSelected,
      z: () => undo(event.shiftKey),
      y: () => undo(true),
      b: () => {
        state.blackout = !state.blackout;
        render();
      },
      w: () => {
        state.window.preset = (state.window.preset + 1) % WINDOWS.length;
        applyPreset(state.image && state.image.frame);
        render();
      },
      f: () => {
        fit();
        render();
      },
      1: () => {
        const { width, height } = canvas.getBoundingClientRect();
        zoomAt(1 / state.view.scale, width / 2, height / 2);
      },
      enter: () => decide("confirmed"),
      r: () => decide("rejected"),
      u: () => decide(null),
      s: openSummary,
      "?": () => $("help").showModal(),
      escape: () => {
        state.selected = null;
        render();
      },
    };
    const action = actions[lower] || actions[key];
    if (action && !event.ctrlKey && !event.metaKey && !event.altKey) {
      event.preventDefault();
      action();
    }
  });
  document.addEventListener("keyup", (event) => {
    if (event.key === " ") state.space = false;
  });

  // The summary: every region dropped and drawn, magnified, for a last check.

  async function openSummary() {
    const dialog = $("summary");
    const counts = { accepted: 0, revised: 0, rejected: 0, none: 0 };
    for (const instance of state.instances) {
      counts[state.work.get(instance.position).redaction || "none"] += 1;
    }
    $("summary-counts").textContent =
      `${counts.accepted} accepted as proposed, ${counts.revised} with your regions, ` +
      `${counts.rejected} rejected, and ${counts.none} without a verdict, which stay held.`;
    $("attest-command").textContent =
      "python -m pymedphys._dicom.deidentify.attestation_command PACK --reviewer NAME " +
      "--outcome attested --reviewed-retained-strings --reviewed-series " +
      "--reviewed-high-risk-instances --redaction-verdicts";
    const crops = $("crops");
    crops.replaceChildren();
    dialog.showModal();
    for (const instance of state.instances) {
      const work = state.work.get(instance.position);
      const entries = [];
      for (const [frame, keys] of work.dropped) {
        for (const key of keys) entries.push({ frame, box: key.split(",").map(Number), kind: "dropped" });
      }
      for (const [frame, boxes] of work.drawn) {
        for (const box of boxes) entries.push({ frame, box, kind: "drawn" });
      }
      entries.sort((a, b) => a.frame - b.frame);
      for (const entry of entries) {
        let frame;
        try {
          frame = await loadFrame(instance.position, entry.frame);
        } catch (error) {
          toast(error.message, true);
          continue;
        }
        crops.append(cropOf(instance, frame, entry));
      }
    }
    if (!crops.children.length) {
      crops.textContent = "You dropped no finder's region and drew none.";
    }
  }

  function cropOf(instance, frame, entry) {
    const margin = 8;
    const [top, left, bottom, right] = entry.box;
    const y0 = Math.max(0, top - margin);
    const x0 = Math.max(0, left - margin);
    const y1 = Math.min(instance.rows, bottom + margin);
    const x1 = Math.min(instance.columns, right + margin);
    // Each crop is shown as received, in its own frame's percentile window.
    const saved = { blackout: state.blackout, window: { ...state.window } };
    state.blackout = false;
    if (frame.bits === 16) [state.window.low, state.window.high] = percentile(frame);
    const bitmap = bitmapOf(frame, instance, state.work.get(instance.position));
    state.blackout = saved.blackout;
    state.window = saved.window;
    const magnify = Math.max(1, Math.min(8, Math.floor(240 / Math.max(x1 - x0, y1 - y0))));
    const crop = document.createElement("canvas");
    crop.width = (x1 - x0) * magnify;
    crop.height = (y1 - y0) * magnify;
    const cropContext = crop.getContext("2d");
    cropContext.imageSmoothingEnabled = false;
    cropContext.drawImage(bitmap, x0, y0, x1 - x0, y1 - y0, 0, 0, crop.width, crop.height);
    cropContext.strokeStyle = entry.kind === "drawn" ? COLOURS.drawn : COLOURS.dropped;
    cropContext.setLineDash(entry.kind === "drawn" ? [] : [6, 4]);
    cropContext.lineWidth = 2;
    cropContext.strokeRect(
      (left - x0) * magnify + 1,
      (top - y0) * magnify + 1,
      (right - left) * magnify - 2,
      (bottom - top) * magnify - 2,
    );
    const figure = document.createElement("figure");
    figure.className = `crop ${entry.kind}`;
    const caption = document.createElement("figcaption");
    caption.textContent =
      `Instance ${instance.position}, frame ${entry.frame + 1} (index ${entry.frame}): ` +
      `${entry.kind} [${entry.box.join(", ")}]`;
    figure.append(crop, caption);
    figure.addEventListener("click", () => {
      $("summary").close();
      open(state.instances.indexOf(instance), entry.frame);
    });
    return figure;
  }

  // The rest of the page.

  let toastTimer = null;
  function toast(message, error = false) {
    const element = $("toast");
    element.textContent = message;
    element.classList.toggle("error", error);
    element.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => element.classList.add("hidden"), error ? 6000 : 3500);
  }

  $("help-button").addEventListener("click", () => $("help").showModal());
  $("help-close").addEventListener("click", () => $("help").close());
  $("summary-button").addEventListener("click", openSummary);
  $("summary-close").addEventListener("click", () => $("summary").close());
  $("confirm-button").addEventListener("click", () => decide("confirmed"));
  $("reject-button").addEventListener("click", () => decide("rejected"));
  $("undecide-button").addEventListener("click", () => decide(null));
  $("clear-frame-button").addEventListener("click", dropAllHere);
  $("blackout-button").addEventListener("click", () => {
    state.blackout = !state.blackout;
    render();
  });
  $("window-button").addEventListener("click", () => {
    state.window.preset = (state.window.preset + 1) % WINDOWS.length;
    applyPreset(state.image && state.image.frame);
    render();
  });
  $("fit-button").addEventListener("click", () => {
    fit();
    render();
  });
  $("undecided-only").addEventListener("change", renderQueue);
  window.addEventListener("resize", resize);

  async function start() {
    try {
      const session = await (await api("/api/session")).json();
      state.reference = session.reference;
      state.instances = session.instances;
      for (const instance of state.instances) state.work.set(instance.position, workFrom(instance));
    } catch (error) {
      document.body.textContent =
        "The review could not start: " + error.message + ". Open the address that the command printed.";
      return;
    }
    $("pack").textContent = `QC pack ${state.reference}`;
    if (!state.instances.length) {
      document.body.textContent = "The QC pack lists no cleaned instance to review.";
      return;
    }
    const first = state.instances.findIndex((i) => !state.work.get(i.position).redaction);
    state.current = Math.max(0, first);
    resize();
    open(state.current, 0);
    canvas.focus();
  }

  start();
})();
