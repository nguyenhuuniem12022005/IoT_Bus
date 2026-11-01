import numpy as np
from vision_node.counter import DirectionalCounter
from vision_node.detector import Detection


def test_board_alight_and_dead_band():
    c = DirectionalCounter()
    frame = np.zeros((100, 100, 3))
    def step(y):
        return c.update([Detection((40, y-5, 60, y+5), .9)], frame)
    assert [step(y) for y in (70, 55, 50, 49, 40, 30)] == [0, 0, 0, 0, 1, 1]
    assert [step(y) for y in (45, 50, 60, 70)] == [1, 1, 0, 0]
    c.clear_tracks()
    assert step(30) == 0
    assert step(50) == 0
    assert step(70) == 0


def detection(x: float, y: float = 50) -> Detection:
    return Detection((x-5, y-10, x+5, y+10), .9)


def test_right_to_left_then_exit_preserves_occupancy_without_visible_people():
    c = DirectionalCounter(direction='left')
    frame = np.zeros((100, 100, 3))
    assert [c.update([detection(x)], frame) for x in (80, 65, 52, 48, 35, 20)] == [0, 0, 0, 0, 1, 1]
    assert c.entered == 1 and c.exited == 0
    for _ in range(8):
        assert c.update([], frame) == 1
    assert [c.update([detection(x)], frame) for x in (20, 35, 48, 52, 65, 80)] == [1, 1, 1, 1, 0, 0]
    assert c.entered == 1 and c.exited == 1


def test_waiting_in_band_does_not_count_and_brief_loss_keeps_id():
    c = DirectionalCounter(direction='left')
    frame = np.zeros((100, 100, 3))
    for x in (65, 53, 49, 51, 48, 52):
        assert c.update([detection(x)], frame) == 0
    c.update([], frame)
    assert c.update([detection(35)], frame) == 1
    assert c.entered == 1 and len(c.tracks) == 1
    c.clear_tracks()
    assert c.value == 1 and c.entered == 1
    assert c.update([detection(20)], frame) == 1


def test_two_people_opposite_directions_and_reordered_detections():
    c = DirectionalCounter(direction='left', initial_count=1)
    frame = np.zeros((100, 100, 3))
    for i, x in enumerate((80, 65, 52, 38, 20)):
        people = [detection(x, 35), detection(100-x, 65)]
        c.update(people if i % 2 else people[::-1], frame)
    assert c.entered == c.exited == 1 and c.value == 1
    assert len(c.overlay()['tracks']) == 2


def test_expired_track_does_not_create_crossing_and_count_never_negative():
    c = DirectionalCounter(direction='left', max_missed=2)
    frame = np.zeros((100, 100, 3))
    c.update([detection(65)], frame)
    for _ in range(3):
        c.update([], frame)
    assert c.update([detection(35)], frame) == 0
    assert c.update([detection(65)], frame) == 0
    assert c.entered == 0 and c.exited == 1


def test_pipeline_publishes_remaining_count_and_video_overlay(config, camera, publisher):
    from vision_node.main import VisionPipeline
    config['crossing'] = dict(direction='left', initial_count=2)
    class Detector:
        x = .8
        def detect(self, frame):
            h, w = frame.shape[:2]
            return [Detection(((self.x-.04)*w, .3*h, (self.x+.04)*w, .7*h), .9)]
    detector = Detector()
    pipeline = VisionPipeline(config, camera, detector, publisher)
    assert pipeline.person_count == 2
    for i, x in enumerate((.8, .65, .5, .35, .2)):
        detector.x = x
        pipeline.tick(i)
    counts = [data for topic, data in publisher.messages if topic == 'vision/count']
    assert counts[-1]['person_count'] == 3 and counts[-1]['raw_count'] == 1
    overlay = pipeline.video_state[2]
    assert overlay['direction'] == 'left' and overlay['entered'] == 1
    assert len(overlay['tracks'][0]['trail']) == 5
    camera.camera_ok = False
    pipeline.tick(6)
    assert pipeline.person_count == 3
    assert not pipeline.video_state[2]['tracks']


def test_render_directional_overlay_uses_same_video_and_preview(config, camera, publisher):
    from vision_node.main import VisionPipeline
    from vision_node.detector import FakeDetector
    config['crossing'] = dict(direction='left')
    pipeline = VisionPipeline(config, camera, FakeDetector([0]), publisher)
    pipeline.tick(0)
    image = np.asarray(pipeline.streamer.render(camera.frame, [], 0, pipeline.video_state[2]))
    # Vạch đứng giữa khung phải xuất hiện cả khi chưa nhận diện thấy người.
    assert tuple(image[300, 240]) == (255, 224, 75)
    assert np.array_equal(pipeline.annotate(camera.frame, [])[:, :, ::-1], image)
