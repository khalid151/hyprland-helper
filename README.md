# hyprland-helper
A collection of functions to make your life easier in Hyprland.

# Functions
## `last_focused`

Toggle between the two last focused windows.

## `dropdown-term`
Start a floating terminal window as a dropdown-style terminal.
Change the terminal class accordingly. Tested with both alacritty and kitty.

The idea behind it is using tmux as a way to save the terminal session. Toggling it basically saves the session
and closes the terminal window. If there isn't a tmux session, a new one will be created, otherwise, it will load
the last saved session.

These rules are expected to be set:
```
windowrule = pin,class:^(dropdown-term)$
windowrule = dimaround,class:^(dropdown-term)$
windowrule = animation slide top,class:^(dropdown-term)$
windowrule = move 25% 1%,class:^(dropdown-term)$
windowrule = size 50% 35%,class:^(dropdown-term)$
windowrule = plugin:hyprbars:nobar,class:^(dropdown-term)$
windowrule = float,class:^(dropdown-term)$
```

## `focus-monitor`
Focus next or previous monitor and wrap the cursor to the center.

I have `cursor:no_warps` set to true as I don't want mouse to change location when changing focus
on one monitor, but focusing monitors with keyboard, I expect it to be on the other monitor.

## `move-to-monitor`
Does the same thing as `focus-monitor` after moving the currently active window to the next or previous monitor.

## `gaps`
Temporarily change the inner or outer gaps for the current workspace. It doesn't save to config, and reloading resets to the default gaps.

Usage example:
- `hyprland-helper.py gaps inner --increase 10`
- `hyprland-helper.py gaps outer --decrease 5`

## `minimize`
Minimize the currently active window. Moving it to a special workspace named minimize, and saving the current workspace as a tag.

## `unminimize`
Launch a rofi menu with a list of minimized windows.
