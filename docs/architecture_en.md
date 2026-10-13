# Architecture and Communication Flows

The application has two Python processes with different responsibilities:

- `streamdock-n3.service` runs the daemon. It owns the USB HID connection, receives device events, updates key images, and dispatches configured actions.
- `streamdock-n3-gui` is a separate GTK application. It edits the user's configuration and asks systemd to restart the daemon after saving when the service is active.

The daemon communicates with the Stream Dock over two input paths. Button and knob reports arrive through the vendored SDK over USB HID/libusb. Some firmware modes also expose media-key events through Linux evdev; that path is read independently and can be grabbed when matching actions are configured. Display updates travel back to the device over USB HID.

## Service Startup and Device Connection

```mermaid
sequenceDiagram
    autonumber
    participant Systemd as systemd-user
    participant Daemon as Python-daemon
    participant Config as config.json-XDG
    participant Terminal as Terminal-detection
    participant Manager as DeviceManager-SDK
    participant HID as LibUSBHIDAPI
    participant Dock as StreamDock-N3
    participant Reader as SDK-reader-thread
    participant Evdev as evdev-worker

    Systemd->>Daemon: ExecStart streamdock-n3
    Daemon->>Config: load_normalized()
    Config-->>Daemon: pages, keys, actions, terminal
    Daemon->>Terminal: resolve terminal when set to auto
    Terminal-->>Daemon: detected terminal ID
    Daemon->>Config: persist detected terminal if changed
    Daemon->>Manager: enumerate supported VID/PID devices
    Manager->>HID: enumerate_devices(vendor_id, product_id)
    HID->>Dock: enumerate USB HID interfaces
    Dock-->>HID: matching device path and metadata
    HID-->>Manager: device information
    Manager-->>Daemon: StreamDockN3 instance
    Daemon->>HID: open device path
    HID-->>Reader: start asynchronous HID read thread
    HID-->>Dock: periodic heartbeat
    Daemon->>Dock: initialize and set brightness
    loop Each LCD key on the current page
        Daemon->>Dock: render/generate image and set_key_image()
        Dock-->>Daemon: image transfer result
    end
    Daemon->>Reader: register on_input callback
    Daemon->>Evdev: start worker with actions and terminal selection
    Evdev->>Evdev: find Stream Dock /dev/input/event* devices
    opt grab_evdev enabled and evdev actions configured
        Evdev->>Evdev: EVIOCGRAB matching input devices
    end
```

`DeviceManager` creates a device-specific `LibUSBHIDAPI` transport for each enumerated device. Opening the SDK device starts its reader and heartbeat threads. The daemon then initializes the N3, renders the current page, registers its callback, and starts the independent evdev worker.

## Device Input and Action Dispatch

```mermaid
sequenceDiagram
    autonumber
    participant Dock as StreamDock-N3
    participant HID as USB-HID-transport
    participant Reader as SDK-reader-thread
    participant Daemon as Python-daemon
    participant Evdev as evdev-worker
    participant Config as XDG-config-and-actions
    participant Terminal as Selected-terminal
    participant Shell as Command-shell
    participant App as Application-or-xdg-open

    alt Button/knob event over USB HID
        Dock->>HID: HID input report
        HID->>Reader: read_() returns report bytes
        Reader->>Reader: decode_input_event()
        Reader->>Daemon: on_input(device, InputEvent)
        Daemon->>Daemon: event_key() maps event to config key
    else Media-key event over Linux evdev
        Dock->>Evdev: kernel input event on /dev/input/event*
        Evdev->>Evdev: select(), read(), map event_key
        Evdev->>Daemon: dispatch mapped action
    end

    alt Page-navigation action
        Daemon->>Daemon: update current page and action map
        Daemon->>HID: render and send the new page's key images
        HID->>Dock: key image reports and refresh
    else Configured action
        Daemon->>Config: resolve reference ID, if action is a template copy
        Config-->>Daemon: action definition from the user actions directory
        Daemon->>Daemon: validate and dispatch action type
        alt Shell action with output enabled
            Daemon->>Terminal: launch selected emulator with cwd and command
            Terminal->>Shell: execute command
            Shell-->>Terminal: stdout, stderr, and exit status
            Note over Terminal: Output remains visible until the user closes the terminal
        else Shell action without output
            Daemon->>Shell: spawn command in background; stdout/stderr discarded
        else Application launch or URL
            Daemon->>App: Popen(argv, shell=False)
        else Sequence action
            Daemon->>Daemon: run first step, schedule later steps with Timer
        end
    end
```

HID events are decoded by the SDK reader thread before the daemon callback runs. evdev events do not pass through that decoder; the worker maps Linux key codes separately and uses the same action dispatcher. For a shell action with `show_output`, the selected emulator runs the command in a shell, so the command's standard output and error are attached to that terminal rather than a GTK dialog.

## GUI Configuration and Service Restart

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant GUI as GTK-GUI-process
    participant Config as XDG-config-files
    participant Systemd as systemd-user
    participant Daemon as Python-daemon
    participant Dock as StreamDock-N3

    User->>GUI: start streamdock-n3-gui
    GUI->>Config: load_normalized(config.json)
    Config-->>GUI: pages, actions, selected terminal
    GUI->>GUI: enumerate installed terminal emulators for selector
    User->>GUI: choose terminal or edit a key action
    opt Create action from template
        GUI->>Config: copy template to user actions directory by ID
        GUI->>Config: copy template icon to actions/assets/
        GUI->>Config: store action reference on the selected key
    end
    User->>GUI: click Save
    GUI->>Config: atomically write config.json
    opt Daemon service is active
        GUI->>Systemd: systemctl --user restart streamdock-n3.service
        Systemd->>Daemon: stop old process and start new process
        Daemon->>Config: reload config and action definitions
        Daemon->>Dock: reconnect, initialize, and apply current page
        Systemd-->>GUI: restart result
        GUI-->>User: show save/restart status
    end
```

The GUI does not open or control the USB device directly. It writes the user's config and action files; the daemon is the only process that owns the device connection. Action templates are copied into the user's XDG config directory so personal edits do not modify the packaged templates.

## Related Code

- [Daemon lifecycle and action dispatch](../src/streamdock_n3/daemon.py)
- [Terminal discovery and command launching](../src/streamdock_n3/terminals.py)
- [Configuration loading, migration, and action references](../src/streamdock_n3/config.py)
- [GUI and systemd integration](../src/streamdock_n3/gui.py)
- [Vendored device discovery](../src/streamdock_n3/_vendor/StreamDock/DeviceManager.py)
- [Stream Dock service unit](../src/streamdock_n3/_data/streamdock-n3.service)