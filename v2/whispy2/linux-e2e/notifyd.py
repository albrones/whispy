# A minimal notification daemon that records each Notify call, one line each.
import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
IFACE = "org.freedesktop.Notifications"


class Daemon(dbus.service.Object):
    count = 0

    def __init__(self, bus):
        dbus.service.Object.__init__(self, dbus.service.BusName(IFACE, bus), "/org/freedesktop/Notifications")

    @dbus.service.method(IFACE, in_signature="susssasa{sv}i", out_signature="u")
    def Notify(self, app, replaces, icon, summary, body, actions, hints, timeout):
        Daemon.count += 1
        print(f"{app} | {summary} | {body}", flush=True)
        return Daemon.count

    @dbus.service.method(IFACE, out_signature="as")
    def GetCapabilities(self):
        return ["body"]

    @dbus.service.method(IFACE, out_signature="ssss")
    def GetServerInformation(self):
        return ("e2e", "whispy", "1", "1.2")

    @dbus.service.method(IFACE, in_signature="u")
    def CloseNotification(self, id):
        pass


Daemon(dbus.SessionBus())
GLib.MainLoop().run()
