#!/bin/env python3
import argparse
import json
import socket
import sys
from os import environ as env
from subprocess import Popen as run, run as b_run
from typing import Literal


class Hyprctl:
    def __init__(self, path: str):
        self.socket_path = path
        self._connect()

    def _connect(self):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.connect(self.socket_path)

    def _close(self):
        self.socket.close()

    def _send(self, command: str) -> str:
        self._connect()
        self.socket.sendall(command.encode())
        reply = b''
        while True:
            recv = self.socket.recv(1024)
            if not recv:
                break
            reply += recv
        self._close()
        return reply.decode()

    def command(self, command: str) -> dict | list[dict]:
        reply = self._send(f"j/{command}")
        return json.loads(reply)

    def batch_json(self, *commands: str) -> list[dict]:
        cmd = "[[BATCH]]j/" + ";j/".join(commands)
        reply = self._send(cmd)
        return [json.loads(j) for j in reply.split('\n\n')]

    def batch(self, *commands: str):
        cmd = ";".join(commands)
        self._send("[[BATCH]]" + cmd)

    def dispatch(self, *args: str):
        cmd = "dispatch " + ' '.join(args)
        self._send(cmd)

    def keyword(self, command: str):
        cmd = "keyword " + command
        self._send(cmd)


def socket_path() -> str:
    try:
        return f"{env['XDG_RUNTIME_DIR']}/hypr/{
                env['HYPRLAND_INSTANCE_SIGNATURE']}/.socket.sock"
    except KeyError as e:
        print(e, "is not set", file=sys.stderr)
        sys.exit(1)


def last_focused(hyprctl: Hyprctl):
    """
    Toggle focus between the two last windows on a workspace
    """
    clients, activeworkspace = hyprctl.batch_json("clients", "activeworkspace")
    worksapce_id = activeworkspace['id']
    workspace_clients = filter(lambda c:
                               c['workspace']['id'] == worksapce_id, clients)
    sorted_clients = sorted(workspace_clients,
                            key=lambda c: c['focusHistoryID'])
    try:
        last_client = sorted_clients[1]
        hyprctl.dispatch("focuswindow", "address:" + last_client['address'])
    except IndexError:
        pass


def dropdown_terminal(hyprctl: Hyprctl, terminal_name: str, session: str):
    """
    Start a floating terminal as window as a dropdown-style terminal

    Following rules are expected to be applied:

    windowrulev2 = pin,class:^(dropdown-term)$
    windowrulev2 = dimaround,class:^(dropdown-term)$
    windowrulev2 = animation slide top,class:^(dropdown-term)$
    windowrulev2 = move 25% 1%,class:^(dropdown-term)$
    windowrulev2 = size 50% 35%,class:^(dropdown-term)$
    windowrulev2 = plugin:hyprbars:nobar,class:^(dropdown-term)$
    windowrulev2 = float,class:^(dropdown-term)$
    """
    terminal_class = "dropdown-term"
    terminal = filter(lambda c: c['class'] == terminal_class,
                      hyprctl.command("clients"))
    try:
        if next(terminal):
            run(["tmux", "detach", "-s", session])
    except StopIteration:
        run([terminal_name, "--class", terminal_class,
             "-e", "sh", "-c",
             f"tmux attach -t {session} || tmux new-session -s {session}"])


def wrap_mouse_to_monitor(hyprctl: Hyprctl, m: dict):
    transform = m['transform']
    width, height = (m['width'], m['height']) if transform not in [1, 3, 5, 7]\
        else (m['height'], m['width'])
    x, y = m['x'], m['y']
    cursor_x = int(width/2 + x)
    cursor_y = int(height/2 + y)
    hyprctl.dispatch(f"movecursor {cursor_x} {cursor_y}")


def focus_monitor(hyprctl: Hyprctl, next_monitor: bool):
    """
    Focus the next or previous monitor and center the mouse cursor
    """
    hyprctl.dispatch("focusmonitor", "+1" if next_monitor else "-1")
    m = next(filter(lambda m: m['focused'], hyprctl.command("monitors")))
    wrap_mouse_to_monitor(hyprctl, m)


def move_to_monitor(hyprctl: Hyprctl, next_monitor: bool):
    """
    Move current client to next/previous monitor
    """
    client, workspaces, monitors = hyprctl.batch_json("activewindow",
                                                      "workspaces",
                                                      "monitors")
    monitor_name = next(filter(lambda w: w['id'] == client['workspace']['id'],
                               workspaces))['monitor']
    index, _ = next(filter(lambda m: m[-1]['name'] == monitor_name,
                           enumerate(monitors)))

    if next_monitor:
        index += 1
    else:
        index -= 1

    monitor = monitors[index % len(monitors)]
    workspace_id = monitor['activeWorkspace']['id']
    hyprctl.dispatch("movetoworkspace", str(workspace_id))
    wrap_mouse_to_monitor(hyprctl, monitor)


def minimize(hyprctl: Hyprctl):
    """
    Minimized active window
    """
    client = hyprctl.command("activewindow")
    if not client:
        return
    workspace_id = client['workspace']['id']
    hyprctl.batch(f"dispatch tagwindow +workspace:{workspace_id}",
                  "dispatch movetoworkspacesilent special:minimized")


def unminimize(hyprctl: Hyprctl):
    """
    Open a rofi menu to select clients to unminimize
    """
    clients = filter(lambda c: c['workspace']['name'] == "special:minimized",
                     hyprctl.command("clients"))
    clients = list(clients)
    menu_items = [f"{c['title']}\u0000icon\u001f{c['class']}"
                  for c in clients]
    if not menu_items:
        return
    res = b_run(["rofi", "-p", "󱂬  Restore", "-i", "-dmenu", "-format", "i"],
                input="\n".join(menu_items), capture_output=True, text=True)
    if not res.stdout:
        return
    index = int(res.stdout.strip())
    client = clients[index]
    tag = next(filter(lambda t: t.startswith("workspace:"), client['tags']))
    address = client['address']
    workspace_id = tag.split(':')[-1]

    untag_cmd = f"tagwindow -workspace:{workspace_id} address:{address}"
    move_cmd = f"movetoworkspace {workspace_id},address:{address}"

    hyprctl.batch(f"dispatch {untag_cmd}", f"dispatch {move_cmd}")


def gaps_control(hyprctl: Hyprctl,
                 location: Literal["inner", "outer"],
                 action: Literal["increase", "decrease"],
                 amount: int, exclude_workspace: [int]):
    reply = hyprctl.batch_json("activeworkspace",
                               "workspacerules",
                               "getoption general:gaps_in",
                               "getoption general:gaps_out",
                               "getoption general:border_size")
    workspace, rules, gaps_in_d, gaps_out_d, border = reply

    workspace_id = workspace['id']
    current_rules = filter(lambda w: w['workspaceString'] == str(workspace_id),
                           rules)
    current_rules = next(current_rules)
    try:
        gaps_in = int(current_rules['gapsIn'][0])
        gaps_out = int(current_rules['gapsOut'][0])
    except KeyError:
        # default gaps
        gaps_out = int(gaps_out_d['custom'].split(' ')[0])
        gaps_in = int(gaps_in_d['custom'].split(' ')[0])

    new_gaps = gaps_in if location == "inner" else gaps_out
    if action == "increase":
        new_gaps += amount
    elif action == "decrease":
        new_gaps = max(0, new_gaps - amount)
    else:
        return
    if location == "inner":
        gaps_in = new_gaps
    else:
        gaps_out = new_gaps

    if workspace_id in exclude_workspace:
        return

    if gaps_out == 0:
        gaps_in = 0
    elif gaps_out > 0 and gaps_in == 0 and location == "outer":
        gaps_in = int(gaps_in_d['custom'].split(' ')[0])

    rounding = True if gaps_in > 0 else False

    hyprctl.keyword(f"workspace {workspace_id}, gapsin:{gaps_in},\
            gapsout:{gaps_out}, rounding:{rounding}".lower())


def gaps_increase(hyprctl: Hyprctl,
                  location, amount: int, exclude_workspace=[]):
    gaps_control(hyprctl, location, "increase", amount, exclude_workspace)


def gaps_decrease(hyprctl: Hyprctl,
                  location, amount: int, exclude_workspace=[]):
    gaps_control(hyprctl, location, "decrease", amount, exclude_workspace)


def main():
    hyprctl = Hyprctl(socket_path())

    parser = argparse.ArgumentParser(prog='Hyprland helper')
    actions_parser = parser.add_subparsers(dest="action", required=True)

    actions_parser.add_parser("last-focused",
                              help="Toggle between the last two windows")

    dropdown_term_parser = actions_parser.add_parser("dropdown-term",
                                                     help="Dropdown terminal")
    dropdown_term_parser.add_argument("-t", "--terminal",
                                      type=str, default="alacritty")
    dropdown_term_parser.add_argument("-s", "--session",
                                      type=str, default="hypr",
                                      help="tmux session name")

    focus_mon_parser = actions_parser.add_parser("focus-monitor",
                                                 help="Focuse next or previous\
                                                         monitor and center\
                                                         the mouse cursor")
    focus_mon_pg = focus_mon_parser.add_mutually_exclusive_group(required=True)
    focus_mon_pg.add_argument("-n", "--next", action="store_true")
    focus_mon_pg.add_argument("-p", "--previous", action="store_true")

    move_to_mon_p = actions_parser.add_parser("move-to-monitor",
                                              help="Move active window to next\
                                                      or previous monitor")
    move_to_mon_pg = move_to_mon_p.add_mutually_exclusive_group(required=True)
    move_to_mon_pg.add_argument("-n", "--next", action="store_true")
    move_to_mon_pg.add_argument("-p", "--previous", action="store_true")

    gaps_parser = actions_parser.add_parser("gaps",
                                            help="Control gaps termoporarily")
    gaps_parser.add_argument("type", choices=["inner", "outer"],
                             help="Specify gaps")
    gaps_group = gaps_parser.add_mutually_exclusive_group(required=True)
    gaps_group.add_argument("-i", "--increase", type=int)
    gaps_group.add_argument("-d", "--decrease", type=int)
    gaps_parser.add_argument("-e", "--exclude",
                             type=lambda s: [int(x) for x in s.split(',')],
                             default=[])

    actions_parser.add_parser("minimize", help="Minimize active window")
    actions_parser.add_parser("unminimize",
                              help="Open rofi menu of minimized windows")

    args = parser.parse_args()

    match args.action:
        case "dropdown-term":
            dropdown_terminal(hyprctl, args.terminal, args.session)
        case "focus-monitor":
            focus_monitor(hyprctl, args.next)
        case "move-to-monitor":
            move_to_monitor(hyprctl, args.next)
        case "gaps":
            if args.increase:
                gaps_increase(hyprctl, args.type, args.increase, args.exclude)
            elif args.decrease:
                gaps_decrease(hyprctl, args.type, args.decrease, args.exclude)
        case "last-focused":
            last_focused(hyprctl)
        case "minimize":
            minimize(hyprctl)
        case "unminimize":
            unminimize(hyprctl)


if __name__ == "__main__":
    main()
