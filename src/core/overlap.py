#!/usr/bin/env python3
"""Geometric frame-to-frame overlap estimation.

Feature matching (ORB / SIFT) -> Lowe ratio test -> RANSAC homography ->
corner warp -> convex intersection. Returns the fraction of the previous
frame still visible in the current frame, used by the adaptive extractor to
decide when to keep a frame.
"""


class OverlapEstimator:
    """
    Compute the fraction of the previous frame that remains visible in the
    current frame, via feature matching + RANSAC homography + corner warp.

    Detector choices:
      "ORB"  -- cv2.ORB_create + BF Hamming matcher (CPU)
                cv2.cuda_ORB                         (GPU, when available)
      "SIFT" -- cv2.SIFT_create + BF L2 matcher     (CPU only)
    """

    def __init__(self, detector="ORB", prefer_cuda=False,
                 nfeatures=2000, downsample_long_side=720):
        from .imports import _try_import_cv2
        cv2, np, err = _try_import_cv2()
        if cv2 is None:
            raise RuntimeError(
                "Adaptive mode requires opencv-python. Install with:\n"
                "    pip install opencv-python numpy\n"
                f"(import error: {err})"
            )
        self.cv2 = cv2
        self.np = np
        self.detector_name = detector.upper()
        self.downsample = int(downsample_long_side)

        cuda_ok = False
        if prefer_cuda and self.detector_name == "ORB":
            try:
                cuda_ok = cv2.cuda.getCudaEnabledDeviceCount() > 0
            except Exception:  # noqa: BLE001
                cuda_ok = False
        self.use_cuda = cuda_ok

        if self.detector_name == "ORB":
            if self.use_cuda:
                self._orb_g = cv2.cuda_ORB.create(nfeatures=nfeatures)
                self._matcher_g = (
                    cv2.cuda.DescriptorMatcher_createBFMatcher(cv2.NORM_HAMMING)
                )
            else:
                self._orb = cv2.ORB_create(nfeatures=nfeatures)
                self._matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        elif self.detector_name == "SIFT":
            try:
                self._sift = cv2.SIFT_create(nfeatures=nfeatures)
            except AttributeError as e:
                raise RuntimeError(
                    "SIFT not available in this OpenCV build. Install "
                    "opencv-contrib-python or upgrade opencv-python (>=4.4)."
                ) from e
            self._matcher = cv2.BFMatcher(cv2.NORM_L2)
        else:
            raise ValueError(f"Unknown detector: {detector!r}")

    @property
    def description(self):
        if self.detector_name == "ORB":
            return f"ORB ({'cv2.cuda GPU' if self.use_cuda else 'CPU'})"
        return "SIFT (CPU)"

    def _prep_gray(self, frame_bgr):
        cv2 = self.cv2
        h, w = frame_bgr.shape[:2]
        long_side = max(h, w)
        if long_side > self.downsample:
            s = self.downsample / long_side
            new_w, new_h = int(round(w * s)), int(round(h * s))
            frame_bgr = cv2.resize(
                frame_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA
            )
        return cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

    def features(self, frame_bgr):
        """Detect+describe; returns an opaque dict consumed by overlap()."""
        cv2 = self.cv2
        gray = self._prep_gray(frame_bgr)
        h, w = gray.shape[:2]
        if self.detector_name == "ORB" and self.use_cuda:
            gpu = cv2.cuda_GpuMat()
            gpu.upload(gray)
            kps_g, desc_g = self._orb_g.detectAndComputeAsync(gpu, None)
            kps = self._orb_g.convert(kps_g)
            return {
                "kp": kps, "desc_g": desc_g, "desc": None, "shape": (h, w),
            }
        if self.detector_name == "ORB":
            kps, desc = self._orb.detectAndCompute(gray, None)
        else:  # SIFT
            kps, desc = self._sift.detectAndCompute(gray, None)
        return {"kp": kps, "desc_g": None, "desc": desc, "shape": (h, w)}

    @staticmethod
    def _ratio_filter(matches, ratio=0.75):
        good = []
        for pair in matches:
            if len(pair) < 2:
                continue
            m, n = pair
            if m.distance < ratio * n.distance:
                good.append(m)
        return good

    def overlap(self, fa, fb):
        """
        Return the fraction of frame B's area that lies inside frame A.
        i.e. how much of B is also seen in A. 1.0 == identical view,
        0.0 == disjoint.
        """
        cv2 = self.cv2
        np = self.np
        if fa is None or fb is None:
            return 0.0

        # --- match descriptors ---
        try:
            if self.use_cuda:
                if fa["desc_g"] is None or fb["desc_g"] is None:
                    return 0.0
                # cv2.cuda GpuMat.size() returns a (w, h) tuple in modern
                # OpenCV (no .width attr); .empty() is the robust empty check.
                if fa["desc_g"].empty() or fb["desc_g"].empty():
                    return 0.0
                matches = self._matcher_g.knnMatch(fb["desc_g"], fa["desc_g"], k=2)
            else:
                if fa["desc"] is None or fb["desc"] is None:
                    return 0.0
                if len(fa["desc"]) < 4 or len(fb["desc"]) < 4:
                    return 0.0
                matches = self._matcher.knnMatch(fb["desc"], fa["desc"], k=2)
        except cv2.error:
            return 0.0

        good = self._ratio_filter(matches, ratio=0.75)
        if len(good) < 8:
            return 0.0

        kpA = fa["kp"]
        kpB = fb["kp"]

        def _pt(kp_list, idx):
            kp = kp_list[idx]
            # cuda_ORB.convert returns numpy array of [x,y,...] rows; cpu kps
            # are KeyPoint objects with .pt
            if hasattr(kp, "pt"):
                return kp.pt
            return (float(kp[0]), float(kp[1]))

        ptsA = np.float32([_pt(kpA, m.trainIdx) for m in good]).reshape(-1, 1, 2)
        ptsB = np.float32([_pt(kpB, m.queryIdx) for m in good]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(ptsB, ptsA, cv2.RANSAC, 3.0)
        if H is None:
            return 0.0

        hb, wb = fb["shape"]
        ha, wa = fa["shape"]
        cornersB = np.float32(
            [[0, 0], [wb, 0], [wb, hb], [0, hb]]
        ).reshape(-1, 1, 2)
        try:
            warped = cv2.perspectiveTransform(cornersB, H).reshape(-1, 2)
        except cv2.error:
            return 0.0
        rectA = np.float32([[0, 0], [wa, 0], [wa, ha], [0, ha]])

        try:
            inter_area, _ = cv2.intersectConvexConvex(warped, rectA)
        except cv2.error:
            return 0.0

        # Sanity: warped quad should be convex and not degenerate.
        # If it's twisted (not convex) or huge, treat as bad estimate.
        if inter_area <= 0:
            return 0.0
        # Normalize against B's full area (mapped via H, but we use B's
        # native pixel area as the denominator: ratio of B that matches A).
        b_area = float(wb * hb)
        if b_area <= 0:
            return 0.0
        ratio = float(inter_area) / b_area
        if ratio > 1.5:  # silly homography
            return 0.0
        return min(1.0, ratio)
