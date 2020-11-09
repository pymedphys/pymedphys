import pathlib
import time

from pymedphys._imports import watchdog

import pymedphys._utilities.filesystem


def read_and_trigger_callback(event, callback):
    event_source_path = pathlib.Path(event.src_path)
    ip = event_source_path.parent.name

    with pymedphys._utilities.filesystem.open_no_lock(  # pylint: disable = protected-access
        event_source_path, "rb"
    ) as f:
        data = f.read()

    callback(ip, data)


def create_event_handler(callback):
    def on_created(event):
        print(f"File created: {event.src_path}")
        read_and_trigger_callback(event, callback)

    def on_deleted(_):
        pass

    def on_modified(event):
        print(f"File modified: {event.src_path}")
        read_and_trigger_callback(event, callback)

    def on_moved(_):
        pass

    event_handler = watchdog.events.PatternMatchingEventHandler(
        patterns="*/[0-2][0-9][0-9].txt",
        ignore_patterns="",
        ignore_directories=True,
        case_sensitive=True,
    )
    event_handler.on_created = on_created
    event_handler.on_deleted = on_deleted
    event_handler.on_modified = on_modified
    event_handler.on_moved = on_moved

    return event_handler


def observe_with_callback(directories_to_watch, callback):
    event_handler = create_event_handler(callback)

    observers = []

    for watch_path in directories_to_watch:
        observer = watchdog.observers.Observer()
        # observer = watchdog.observers.polling.PollingObserver()
        observer.schedule(event_handler, watch_path, recursive=True)

        observers.append(observer)

    for observer in observers:
        observer.start()

    try:
        while True:
            time.sleep(1)
    finally:
        for observer in observers:
            observer.stop()
            observer.join()
