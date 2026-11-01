"""Đo suy luận thực tế; không lưu khung hình."""
import argparse
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision_node.camera import CameraSource
from vision_node.config import ROOT, load_config
from vision_node.detector import YoloV8Detector
from vision_node.utils.logger import configure_console


def main() -> None:
    configure_console()
    import numpy as np
    parser = argparse.ArgumentParser(description='Đo FPS và độ trễ p95, bỏ qua warm-up')
    parser.add_argument('--source')
    parser.add_argument('--frames', type=int, default=100)
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    if args.frames < 1 or args.timeout <= 0:
        parser.error('Số khung và timeout phải dương')
    config = load_config(overrides={'source': args.source})
    model = config['model']
    detector = YoloV8Detector(str(ROOT / model['path']), model['conf'], model['iou'], model['imgsz'], model['device'])
    camera = CameraSource(config['source'], config['frame_width'], config['frame_height'], config['loop_video'])
    latencies: list[float] = []
    camera.start()
    started = time.monotonic()
    try:
        while len(latencies) < args.frames and time.monotonic() - started < args.timeout:
            ok, frame = camera.read()
            if ok:
                begin = time.monotonic()
                detector.detect(frame)
                latencies.append(time.monotonic() - begin)
            else:
                time.sleep(.01)
            if camera.ended:
                break
    except KeyboardInterrupt:
        pass
    finally:
        camera.close()
    if not latencies:
        raise SystemExit('Không nhận được khung; kiểm tra nguồn camera')
    print(f'{len(latencies)} khung; FPS suy luận={len(latencies)/sum(latencies):.2f}; '
          f'FPS toàn luồng={len(latencies)/(time.monotonic()-started):.2f}; '
          f'p95={np.percentile(latencies, 95)*1000:.1f} ms')


if __name__ == '__main__':
    main()
