import base64
import threading
from pathlib import Path

import cv2
import numpy as np


class BiometricAuth:
    sample_size = (160, 160)
    minimum_samples = 12
    confidence_threshold = 65.0

    def __init__(self, storage_dir: Path) -> None:
        self.storage_dir = storage_dir
        self.model_path = storage_dir / "face_model.yml"
        self._camera: cv2.VideoCapture | None = None
        self._camera_lock = threading.Lock()
        self._samples: list[np.ndarray] = []
        self._face_detector = cv2.CascadeClassifier(
            str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        )
        if self._face_detector.empty():
            raise RuntimeError("Model deteksi wajah OpenCV tidak dapat dimuat.")
        if not hasattr(cv2, "face"):
            raise RuntimeError(
                "Modul pengenal wajah tidak tersedia. Instal opencv-contrib-python."
            )

    def start_camera(self) -> str:
        with self._camera_lock:
            if self._camera is not None and self._camera.isOpened():
                return "Webcam sudah aktif."

            backend = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") else 0
            camera = cv2.VideoCapture(0, backend)
            if not camera.isOpened():
                camera.release()
                raise RuntimeError(
                    "Webcam tidak dapat dibuka. Periksa koneksi dan izin kamera."
                )
            self._camera = camera
        return "Webcam aktif."

    def stop_camera(self) -> None:
        with self._camera_lock:
            if self._camera is not None:
                self._camera.release()
                self._camera = None

    def _read_frame(self) -> np.ndarray:
        with self._camera_lock:
            if self._camera is None or not self._camera.isOpened():
                raise RuntimeError("Aktifkan webcam terlebih dahulu.")
            success, frame = self._camera.read()
        if not success:
            raise RuntimeError("Gagal membaca gambar dari webcam.")
        return frame

    def camera_frame(self) -> str:
        frame = self._read_frame()
        success, encoded = cv2.imencode(
            ".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 75]
        )
        if not success:
            raise RuntimeError("Gambar webcam gagal diproses.")
        return "data:image/jpeg;base64," + base64.b64encode(encoded).decode("ascii")

    def _face_sample(self, frame: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = self._face_detector.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(80, 80),
        )
        if len(faces) == 0:
            raise ValueError("Wajah tidak terdeteksi. Atur pencahayaan dan posisi kamera.")

        x, y, width, height = max(faces, key=lambda face: face[2] * face[3])
        face = gray[y : y + height, x : x + width]
        face = cv2.resize(face, self.sample_size, interpolation=cv2.INTER_AREA)
        return cv2.equalizeHist(face)

    def capture_enrollment_sample(self) -> dict[str, int | str]:
        if self.model_path.exists():
            raise ValueError("Wajah sudah terdaftar. Hapus data pendaftaran lama dahulu.")
        sample = self._face_sample(self._read_frame())
        self._samples.append(sample)
        return {"count": len(self._samples), "required": self.minimum_samples}

    def finish_enrollment(self) -> str:
        if len(self._samples) < self.minimum_samples:
            raise ValueError(
                f"Ambil minimal {self.minimum_samples} sampel wajah terlebih dahulu."
            )

        self.storage_dir.mkdir(parents=True, exist_ok=True)
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        labels = np.ones(len(self._samples), dtype=np.int32)
        recognizer.train(self._samples, labels)
        recognizer.write(str(self.model_path))
        self._samples.clear()
        return "Pendaftaran wajah selesai."

    def is_registered(self) -> bool:
        return self.model_path.is_file()

    def verify(self) -> dict[str, float | bool | str]:
        if not self.is_registered():
            raise ValueError("Wajah belum didaftarkan.")

        sample = self._face_sample(self._read_frame())
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        try:
            recognizer.read(str(self.model_path))
        except cv2.error as error:
            raise RuntimeError("Data biometrik wajah tidak dapat dibaca.") from error

        label, confidence = recognizer.predict(sample)
        verified = label == 1 and confidence <= self.confidence_threshold
        return {
            "verified": verified,
            "confidence": round(float(confidence), 1),
            "message": (
                "Wajah cocok."
                if verified
                else "Wajah tidak cocok. Coba lagi dengan posisi dan pencahayaan yang baik."
            ),
        }