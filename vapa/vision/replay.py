"""RealSense recording and offline replay harness for testing without live camera."""

from pathlib import Path
from typing import List, Tuple, Optional, Generator
import numpy as np
from .filters import SoftwareDepthFilter, FilterConfig
from .distance_matrix import DistanceMatrixProcessor, DistanceMatrixResult

class VisionSequenceRecorder:
    """Records RGB and Depth frame sequences into portable .npz archives."""

    def __init__(self):
        self.color_frames: List[np.ndarray] = []
        self.depth_frames: List[np.ndarray] = []
        self.timestamps: List[float] = []

    def record_frame(self, color: np.ndarray, depth_m: np.ndarray, timestamp: float) -> None:
        self.color_frames.append(color.astype(np.uint8))
        self.depth_frames.append(depth_m.astype(np.float32))
        self.timestamps.append(float(timestamp))

    def save(self, filepath: Path) -> None:
        """Save captured sequence to compressed .npz archive."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            filepath,
            color=np.array(self.color_frames),
            depth=np.array(self.depth_frames),
            timestamps=np.array(self.timestamps),
        )

    @staticmethod
    def create_synthetic_sequence(
        filepath: Path,
        num_frames: int = 60,
        fps: float = 30.0,
        start_dist_m: float = 0.65,
        end_dist_m: float = 0.22,
    ) -> None:
        """Generate and save a synthetic approaching target sequence."""
        rec = VisionSequenceRecorder()
        dt = 1.0 / fps

        # Target travels linearly from start_dist to end_dist
        distances = np.linspace(start_dist_m, end_dist_m, num_frames)

        for i, dist in enumerate(distances):
            t = i * dt
            # Background at 2.2 meters
            depth = np.full((480, 640), 2.2, dtype=np.float32)
            color = np.full((480, 640, 3), 40, dtype=np.uint8)

            # Center target: 120x120 pixels in center
            cy, cx = 240, 320
            r = 60
            # Target surface with subtle depth curvature
            depth[cy - r : cy + r, cx - r : cx + r] = dist
            color[cy - r : cy + r, cx - r : cx + r] = [0, 180, 180]

            # Inject small camera noise (dropouts / holes)
            noise_mask = np.random.rand(480, 640) < 0.01
            depth[noise_mask] = 0.0

            rec.record_frame(color, depth, t)

        rec.save(filepath)

class VisionReplayHarness:
    """Offline test harness feeding recorded or synthetic sequences through filters and distance matrix."""

    def __init__(
        self,
        sequence_path: Path,
        filter_config: FilterConfig = FilterConfig(),
        grid_rows: int = 12,
        grid_cols: int = 16,
    ):
        if not sequence_path.exists():
            raise FileNotFoundError(f"Sequence archive not found: {sequence_path}")

        data = np.load(sequence_path)
        self.colors = data["color"]
        self.depths = data["depth"]
        self.timestamps = data["timestamps"]
        self.num_frames = len(self.timestamps)

        self.filter = SoftwareDepthFilter(filter_config)
        self.processor = DistanceMatrixProcessor(grid_rows=grid_rows, grid_cols=grid_cols)

    def __len__(self) -> int:
        return self.num_frames

    def stream(self) -> Generator[Tuple[int, DistanceMatrixResult, float], None, None]:
        """Stream frames through filtering and distance matrix processing.

        Yields:
            (frame_idx, DistanceMatrixResult, timestamp)
        """
        for i in range(self.num_frames):
            color = self.colors[i]
            raw_depth = self.depths[i]
            t = float(self.timestamps[i])

            filtered_depth = self.filter.process(raw_depth)
            result = self.processor.process(filtered_depth, timestamp=t)
            yield i, result, t
