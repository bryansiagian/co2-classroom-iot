import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]

def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

class GatewayTests(unittest.TestCase):
    def test_validation(self):
        local = load('local_relay')
        valid = b'{"co2":700,"temperature":26,"humidity":60,"pir":0}'
        self.assertTrue(local.valid_payload(valid))
        self.assertFalse(local.valid_payload(b'{}'))
        self.assertFalse(local.valid_payload(b'not-json'))
        remote = load('remote_sink')
        self.assertEqual(remote.validate({'id':1, 'topic':local.TOPIC,'payload':valid.decode()})[0],1)
        with self.assertRaises(ValueError):
            remote.validate({'id':1,'topic':'other','payload':valid.decode()})

    def test_queue(self):
        local = load('local_relay')
        with tempfile.TemporaryDirectory() as temp:
            conn = local.init_db(Path(temp) / 'queue.db')
            conn.execute('INSERT INTO pending(topic,payload) VALUES (?,?)', (local.TOPIC, '{}'))
            conn.commit()
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM pending').fetchone()[0], 1)
            conn.close()

if __name__ == '__main__':
    unittest.main()
