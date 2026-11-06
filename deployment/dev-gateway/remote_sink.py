#!/usr/bin/env python3
"""H200 side: consume JSON lines from SSH stdin and publish to existing TLS broker.
Uses the existing backend Python venv (paho-mqtt and python-dotenv).
"""
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOPIC = 'classroom/gd525/sensors'

def broker_config():
    username = os.environ.get('MQTT_USERNAME') or os.environ.get('MQTT_USER')
    password = os.environ.get('MQTT_PASSWORD')
    if not username or not password:
        raise RuntimeError('MQTT_USERNAME and MQTT_PASSWORD must be defined in backend/.env or environment')
    return {
        'host': os.environ.get('MQTT_HOST', '172.22.44.29'),
        'port': int(os.environ.get('MQTT_PORT', '8883')),
        'username': username,
        'password': password,
        'ca': ROOT / 'backend' / 'backend' / (os.environ.get('MQTT_CA_CERT', 'certs/server.crt')),
    }


def validate(msg):
    if not isinstance(msg, dict) or not isinstance(msg.get('id'), int) or msg['id'] <= 0:
        raise ValueError('invalid id')
    if msg.get('topic') != TOPIC:
        raise ValueError('forbidden topic')
    payload = msg.get('payload')
    if not isinstance(payload, str) or len(payload.encode('utf-8')) > 4096:
        raise ValueError('invalid payload')
    doc = json.loads(payload)
    if not isinstance(doc, dict):
        raise ValueError('invalid sensor JSON')
    for name in ('co2', 'temperature', 'humidity', 'pir'):
        if name not in doc:
            raise ValueError(f'missing sensor field {name}')
    return msg['id'], payload


def main():
    try:
        from dotenv import load_dotenv
        import paho.mqtt.client as mqtt
    except ImportError as exc:
        sys.stderr.write(f"Missing dependency in H200 backend venv: {exc}\n")
        raise SystemExit(2)
    load_dotenv(ROOT / 'backend' / '.env', override=False)
    cfg = broker_config()
    if not cfg['ca'].is_file():
        raise RuntimeError(f'TLS CA file not found: {cfg["ca"]}')
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=f'gd525-dev-relay-{os.getpid()}')
    client.username_pw_set(cfg['username'], cfg['password'])
    client.tls_set(ca_certs=str(cfg['ca']))
    client.connect(cfg['host'], cfg['port'], keepalive=45)
    client.loop_start()
    try:
        for line in sys.stdin:
            try:
                msg_id, payload = validate(json.loads(line))
                result = client.publish(TOPIC, payload, qos=1, retain=False)
                result.wait_for_publish(timeout=15)
                if not result.is_published() or result.rc != mqtt.MQTT_ERR_SUCCESS:
                    raise RuntimeError(f'MQTT publish failed: {result.rc}')
                print(json.dumps({'id': msg_id, 'ok': True}), flush=True)
            except Exception as exc:
                sys.stderr.write(f'Remote sink error: {type(exc).__name__}: {exc}\n')
                # Do not ack; local SQLite queue will retry on next connection
                raise SystemExit(3)
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == '__main__':
    main()
