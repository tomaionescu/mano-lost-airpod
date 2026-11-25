"""Run MediaPipe Face Landmarker on reference photos; writes <photo>.lm.json with 478 landmarks
(pixel x, pixel y, z in pixel units), the 52 blendshape scores and the facial transformation matrix."""
import json, sys, os
import numpy as np, cv2
import mediapipe as mp
from mediapipe.tasks import python as mpt
from mediapipe.tasks.python import vision

MODEL = os.path.join(os.path.dirname(__file__), '..', 'models', 'face_landmarker.task')

def detect(path):
    img = cv2.imread(path, cv2.IMREAD_COLOR)
    if img is None:  # webp etc.
        from PIL import Image
        img = cv2.cvtColor(np.array(Image.open(path).convert('RGB')), cv2.COLOR_RGB2BGR)
    h, w = img.shape[:2]
    opts = vision.FaceLandmarkerOptions(base_options=mpt.BaseOptions(model_asset_path=MODEL),
                                        output_face_blendshapes=True, output_facial_transformation_matrixes=True, num_faces=4)
    with vision.FaceLandmarker.create_from_options(opts) as lm:
        res = lm.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))
    faces = []
    for i, f in enumerate(res.face_landmarks):
        pts = [[p.x * w, p.y * h, p.z * w] for p in f]
        xs = [p[0] for p in pts]
        faces.append({'pts': pts, 'width': max(xs) - min(xs),
                      'blend': {b.category_name: b.score for b in res.face_blendshapes[i]} if res.face_blendshapes else {},
                      'matrix': np.array(res.facial_transformation_matrixes[i]).tolist() if res.facial_transformation_matrixes else None})
    faces.sort(key=lambda f: -f['width'])
    return {'w': w, 'h': h, 'faces': faces}

if __name__ == '__main__':
    for p in sys.argv[1:]:
        r = detect(p)
        json.dump(r, open(p + '.lm.json', 'w'))
        print(os.path.basename(p), r['w'], r['h'], 'faces:', len(r['faces']), 'widths:', [round(f['width']) for f in r['faces']])
