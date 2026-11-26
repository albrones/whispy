# A minimal StatusNotifierWatcher with a host, standing in for a panel's tray.
import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
IFACE = "org.kde.StatusNotifierWatcher"


class Watcher(dbus.service.Object):
    def __init__(self, bus):
        self.items = []
        dbus.service.Object.__init__(self, dbus.service.BusName(IFACE, bus), "/StatusNotifierWatcher")

    @dbus.service.method(IFACE, in_signature="s", sender_keyword="sender")
    def RegisterStatusNotifierItem(self, service, sender=None):
        name = service if service.startswith(":") or "." in service else sender
        self.items.append(name)
        print("registered", name, service, flush=True)
        open("/tmp/sni_item", "w").write(name)

    @dbus.service.method(IFACE, in_signature="s")
    def RegisterStatusNotifierHost(self, service):
        pass

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="ss", out_signature="v")
    def Get(self, iface, prop):
        return {
            "IsStatusNotifierHostRegistered": True,
            "ProtocolVersion": 0,
            "RegisteredStatusNotifierItems": dbus.Array(self.items, signature="s"),
        }[prop]

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, iface):
        return {
            "IsStatusNotifierHostRegistered": True,
            "ProtocolVersion": 0,
            "RegisteredStatusNotifierItems": dbus.Array(self.items, signature="s"),
        }


Watcher(dbus.SessionBus())
GLib.MainLoop().run()
