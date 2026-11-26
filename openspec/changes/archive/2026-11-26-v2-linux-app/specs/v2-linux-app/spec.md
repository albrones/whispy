## ADDED Requirements

### Requirement: Dictation with Right Ctrl under X11
Under an X11 session, `whispy2` SHALL listen to Right Ctrl (keysym `Control_R`) through XInput 2 raw key events selected on the root window, without grabbing the key. Holding it SHALL record and releasing it SHALL insert the text into the focused window (hold mode), or a press SHALL start and the next one stop (toggle mode). An autorepeat of the held key SHALL NOT be a new press, and another key pressed while Right Ctrl is held SHALL cancel the dictation as a shortcut.

#### Scenario: « Ajouter trois tests » under X11
- **WHEN** Right Ctrl is held, « Ajouter trois tests » is spoken and Right Ctrl is released, with a terminal focused
- **THEN** « Ajouter 3 tests. » SHALL be typed into that terminal

_Tier: e2e — `whispy2/linux-e2e/x11.sh` (Xvfb, XTest, PulseAudio null sink, real models)._

#### Scenario: Autorepeat and shortcuts
- **WHEN** the X server repeats the held key, or C goes down while Right Ctrl is held
- **THEN** no second press SHALL be produced, and the C press SHALL be `OtherKeyDown`

_Tier: unit — `linux::x11_trigger` `Decoder`._

### Requirement: Dictation through the control socket under Wayland
Under a Wayland session, `whispy2` SHALL listen to no key: the compositor's binding SHALL drive the dictation through the control socket (`start`, `stop`, `toggle`). The text SHALL be typed with enigo through the virtual-keyboard protocol, one key at a time, and only the Wayland backend SHALL be able to connect (no second copy through XWayland).

#### Scenario: Socket start and stop under Wayland
- **WHEN** `start` is sent to the socket, « Ajouter trois tests » is spoken, then `stop` is sent, with a terminal focused
- **THEN** « Ajouter 3 tests. » SHALL be typed into that terminal

_Tier: e2e — `whispy2/linux-e2e/wayland.sh` (sway headless, foot); Hyprland at the user's recette._

#### Scenario: One backend per session
- **WHEN** enigo's settings are built for a Wayland session
- **THEN** the X11 display name SHALL be one that cannot connect, and the reverse for X11

_Tier: unit — `linux::inserter`._

### Requirement: The X11 tray icon shows the state and offers Quit
Under X11, `whispy2` SHALL show a StatusNotifierItem icon: a grey ring at rest, a red dot while listening; its menu SHALL show the status line and a Quit item that ends Whispy and removes its socket. If the icon cannot start, Whispy SHALL log why, post one notification « Tray icon unavailable », and keep running.

#### Scenario: Icon, menu and Quit
- **WHEN** a panel hosts status icons and Right Ctrl is held, then Quit is clicked
- **THEN** the icon SHALL turn from a grey ring to a red dot, and after Quit the process SHALL have exited and the socket SHALL be gone

_Tier: e2e — `whispy2/linux-e2e/x11.sh` (a minimal watcher, read and clicked over D-Bus)._

#### Scenario: No tray host
- **WHEN** no StatusNotifierWatcher runs
- **THEN** Whispy SHALL keep running, answer on its socket and post exactly one notification « Tray icon unavailable »

_Tier: e2e — `whispy2/linux-e2e/x11-degraded.sh`._

### Requirement: An unavailable X11 key is said, not a crash
If Right Ctrl cannot be listened to (no X server, no XInput 2, no Right Ctrl in the layout, the connection lost later), Whispy SHALL keep running, post a notification « Trigger key unavailable » with a sentence that names the key, the reason and that the socket still works, and show that sentence as the status's last problem.

#### Scenario: X server unreachable
- **WHEN** Whispy starts in an X11 session whose `DISPLAY` answers nothing
- **THEN** it SHALL keep running, its socket status SHALL carry « Whispy cannot listen to the Right Ctrl key: the X server is unreachable … », and one notification SHALL say so

_Tier: e2e — `whispy2/linux-e2e/x11-degraded.sh`._
