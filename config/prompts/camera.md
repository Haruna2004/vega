You are calibrating a camera for road measurement. Look at this frame from a
vehicle-mounted camera and estimate the camera geometry.

Return:
- horizon_y_frac: the image row of the horizon / road vanishing point as a fraction of
  image height (0 = top, 1 = bottom). If the road is hilly, use where the road's
  edges would converge.
- camera_mount: one of dashboard, handheld, dashcam_wide, motorbike, unknown.
- fisheye: true if straight lines are visibly curved (wide-angle distortion).
- confidence: low | medium | high.
- notes: one short sentence.
