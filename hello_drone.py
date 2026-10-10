"""Pierwszy test: połącz się z symulatorem, wystartuj, powiś i lądowanie.

Użycie:  python hello_drone.py --connect tcp:127.0.0.1:5762
"""
import argparse
import time

from pymavlink import mavutil

MAV_CMD_NAV_TAKEOFF = 22
MAV_CMD_COMPONENT_ARM_DISARM = 400
FLAG_ARMED = 128


def czekaj_na_heartbeat(conn):
    print("Czekam na heartbeat z autopilota...")
    hb = conn.wait_heartbeat(timeout=30)
    if hb is None:
        raise SystemExit("Brak heartbeat. Czy symulator działa i czy adres jest poprawny (tcp:127.0.0.1:5762)?")
    print(f"Połączono: system {conn.target_system}, komponent {conn.target_component}")


def czy_uzbrojony(conn, timeout=1.0):
    hb = conn.recv_match(type="HEARTBEAT", blocking=True, timeout=timeout)
    return None if hb is None else bool(hb.base_mode & FLAG_ARMED)


def uzbroj(conn, limit_s=120):
    conn.set_mode("GUIDED")
    cel = (conn.target_system, conn.target_component)
    start = time.time()
    while time.time() - start < limit_s:
        conn.mav.command_long_send(*cel, MAV_CMD_COMPONENT_ARM_DISARM, 0, 1, 0, 0, 0, 0, 0, 0)
        koniec = time.time() + 3
        while time.time() < koniec:
            msg = conn.recv_match(type=["HEARTBEAT", "STATUSTEXT"], blocking=True, timeout=1)
            if msg is None:
                continue
            if msg.get_type() == "STATUSTEXT" and "Arm" in msg.text:
                print("  autopilot:", msg.text)
            if msg.get_type() == "HEARTBEAT" and msg.base_mode & FLAG_ARMED:
                print("Uzbrojony.")
                return
    raise SystemExit("Nie udało się uzbroić w limicie czasu.")


def wysokosc_m(conn):
    msg = conn.recv_match(type="GLOBAL_POSITION_INT", blocking=True, timeout=2)
    return None if msg is None else msg.relative_alt / 1000.0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--connect", default="tcp:127.0.0.1:5762")
    parser.add_argument("--alt", type=float, default=10.0, help="wysokość startu w metrach")
    args = parser.parse_args()

    conn = mavutil.mavlink_connection(args.connect)
    czekaj_na_heartbeat(conn)
    conn.mav.request_data_stream_send(
        conn.target_system, conn.target_component, mavutil.mavlink.MAV_DATA_STREAM_ALL, 4, 1
    )

    uzbroj(conn)

    cel = (conn.target_system, conn.target_component)
    conn.mav.command_long_send(*cel, MAV_CMD_NAV_TAKEOFF, 0, 0, 0, 0, 0, 0, 0, args.alt)
    print(f"Start na {args.alt} m...")
    start = time.time()
    while time.time() - start < 60:
        h = wysokosc_m(conn)
        if h is not None:
            print(f"  wysokość: {h:.1f} m")
            if h >= args.alt * 0.9:
                break
    else:
        raise SystemExit("Dron nie osiągnął wysokości w 60 s.")

    print("Wiszę 5 sekund...")
    time.sleep(5)

    print("Lądowanie.")
    conn.set_mode("LAND")
    while czy_uzbrojony(conn, timeout=2) is not False:
        h = wysokosc_m(conn)
        if h is not None:
            print(f"  wysokość: {h:.1f} m")
    print("Wylądowano i rozbrojono. Koniec.")


if __name__ == "__main__":
    main()