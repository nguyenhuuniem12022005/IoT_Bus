"""Kiểm tra nguồn camera, hiển thị hình và FPS."""
import argparse
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from vision_node.camera import CameraSource
from vision_node.utils.logger import configure_console


def main() -> None:
    configure_console()
    import cv2
    parser = argparse.ArgumentParser(description='Kiểm tra webcam; q để thoát')
    parser.add_argument('--source', default='0')
    args = parser.parse_args()
    camera = CameraSource(int(args.source) if args.source.isdigit() else args.source)
    camera.start()
    started, count = time.monotonic(), 0
    try:
        while True:
            ok, frame = camera.read()
            if ok:
                count += 1
                cv2.imshow('Camera', frame)
                if count % 30 == 0:
                    print(f'FPS trung bình: {count / (time.monotonic() - started):.2f}')
            if cv2.waitKey(1) & 0xFF == ord('q') or camera.ended:
                break
            time.sleep(.01)
    except KeyboardInterrupt:
        pass
    finally:
        camera.close()
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
