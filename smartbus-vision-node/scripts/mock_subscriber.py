"""Giả lập Backend, nghe vision và gửi lệnh từ bàn phím."""
import argparse
import json
import sys
import time
import uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision_node.config import load_config
from vision_node.utils.logger import configure_console


def main() -> None:
    configure_console()
    import paho.mqtt.client as mqtt
    parser = argparse.ArgumentParser(description='Mock Backend; cần tài khoản có ACL Backend')
    parser.add_argument('--username', default='backend')
    parser.add_argument('--password', default=None, help='Bỏ trống để nhập kín từ bàn phím')
    args = parser.parse_args()
    config = load_config()
    settings = config['mqtt']
    prefix = f"smartbus/{config['bus_id']}/"
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id='backend')
    if args.password is None:
        from getpass import getpass
        args.password = getpass('Mật khẩu MQTT Backend (dev có thể để trống): ')
    client.username_pw_set(args.username, args.password)
    if settings['tls']:
        client.tls_set()
    client.reconnect_delay_set(1, 30)

    def on_connect(client: mqtt.Client, userdata: object, flags: object, reason_code: object, properties: object) -> None:
        print(f'Kết nối: {reason_code}')
        if reason_code == 0:
            client.subscribe([(prefix + 'vision/#', 0), (prefix + 'cmd/ack', 1)])

    def on_message(client: mqtt.Client, userdata: object, message: mqtt.MQTTMessage) -> None:
        try:
            if message.topic.endswith('/vision/frame'):
                print(f'Khung JPEG: {len(message.payload)} byte (chỉ trong RAM)')
                return
            payload = json.loads(message.payload)
            print(message.topic, json.dumps(payload, ensure_ascii=False))
        except (ValueError, UnicodeError) as exc:
            print(f'Payload lỗi: {exc}')

    client.on_connect, client.on_message = on_connect, on_message
    client.connect_async(settings['host'], settings['port'], keepalive=30)
    client.loop_start()
    try:
        while True:
            action = input('STREAM_START / STREAM_STOP / PAUSE / RESUME / QUIT (hoặc action sai để thử): ').strip().upper()
            if action == 'QUIT':
                break
            if not client.is_connected():
                print('Chưa nối broker; thử lại sau')
                continue
            client.publish(prefix + 'cmd/vision', json.dumps(dict(cmd_id=str(uuid.uuid4()),
                ts=time.time_ns() // 1_000_000, action=action, params={}, issued_by='mock-backend')), qos=1)
    except (EOFError, KeyboardInterrupt):
        pass
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == '__main__':
    main()
