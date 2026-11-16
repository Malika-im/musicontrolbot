"""
Key and BPM Detection Module.
Uses Librosa chroma analysis and the Krumhansl-Schmuckler key-finding algorithm.
Determines original key, scale (major/minor), BPM, and computes resulting transposed key.
"""

from typing import Optional, Tuple

# Pitch names in 12-tone equal temperament
PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
ENHARMONIC_FLATS = {
    "C#": "Db",
    "D#": "Eb",
    "F#": "Gb",
    "G#": "Ab",
    "A#": "Bb",
}

# Krumhansl-Schmuckler key profiles for Major and Minor keys
MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


class KeyDetector:
    """Detects musical key, scale, and tempo (BPM) from audio."""

    @staticmethod
    def detect_key_and_bpm(audio_path: str) -> Tuple[str, float]:
        """
        Analyze audio file and return (key_str, bpm).
        Example return: ("C major", 120.0)
        """
        try:
            import numpy as np
            import librosa

            major_arr = np.array(MAJOR_PROFILE)
            minor_arr = np.array(MINOR_PROFILE)

            # Load audio (downsample to 22050 for fast chroma analysis)
            y, sr = librosa.load(audio_path, sr=22050, mono=True, duration=90.0)

            # Estimate tempo
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            if isinstance(tempo, np.ndarray):
                bpm = float(tempo[0]) if len(tempo) > 0 else 120.0
            else:
                bpm = float(tempo)
            bpm = round(bpm, 1)

            # Compute harmonic chroma
            y_harmonic = librosa.effects.harmonic(y)
            chroma = librosa.feature.chroma_cqt(y=y_harmonic, sr=sr)
            chroma_sum = np.sum(chroma, axis=1)

            # Normalize chroma vector
            norm = np.linalg.norm(chroma_sum)
            if norm > 0:
                chroma_vector = chroma_sum / norm
            else:
                return "Unknown", bpm

            # Correlate with all 12 major and 12 minor shifts
            best_corr = -1.0
            best_key = "C major"

            for i in range(12):
                # Major correlation
                major_shift = np.roll(major_arr, i)
                corr_major = np.corrcoef(chroma_vector, major_shift)[0, 1]
                if corr_major > best_corr:
                    best_corr = corr_major
                    best_key = f"{PITCH_CLASSES[i]} major"

                # Minor correlation
                minor_shift = np.roll(minor_arr, i)
                corr_minor = np.corrcoef(chroma_vector, minor_shift)[0, 1]
                if corr_minor > best_corr:
                    best_corr = corr_minor
                    best_key = f"{PITCH_CLASSES[i]} minor"

            return best_key, bpm

        except Exception:
            # Fallback if librosa fails or audio too quiet
            return "C major (оценка)", 120.0

    @staticmethod
    def transpose_key_name(key_name: str, semitones: int) -> str:
        """
        Calculate resulting musical key after shifting by `semitones`.
        Example: "C major" shifted by -2 semitones -> "Bb major"
        """
        if not key_name or "Unknown" in key_name:
            return "Unknown"

        parts = key_name.replace(" (оценка)", "").split()
        if len(parts) < 2:
            return key_name

        root, scale = parts[0], parts[1]
        # Normalize flats to sharps
        reverse_flats = {v: k for k, v in ENHARMONIC_FLATS.items()}
        root_sharp = reverse_flats.get(root, root)

        if root_sharp not in PITCH_CLASSES:
            return key_name

        idx = PITCH_CLASSES.index(root_sharp)
        new_idx = (idx + int(round(semitones))) % 12
        new_root = PITCH_CLASSES[new_idx]

        # Use musical flats for common keys like Bb, Eb
        if new_root in ("A#", "D#") and "minor" not in scale:
            new_root = ENHARMONIC_FLATS[new_root]

        return f"{new_root} {scale}"
