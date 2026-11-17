"""DXGI region capture; copy only the small requested ROI into owned PIL memory."""
from PIL import Image


class FrameNotReady(RuntimeError):
    pass


def intersect(a, b):
    box = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return box if box[2] > box[0] and box[3] > box[1] else None


class DesktopCapture:
    def __init__(self, module=None):
        if module is None:
            import dxcam as module
        self.module = module
        self.cameras = {}
        self.last_regions = {}

    def capture_client(self, rect):
        left, top, right, bottom = rect
        if right <= left or bottom <= top:
            raise ValueError("Invalid client rectangle")
        client = Image.new("RGB", (right-left, bottom-top))
        covered = 0
        outputs = []
        # Installed DXcam exposes desktop coordinates through its output descriptors.
        # Keep this version-specific access isolated here; never assume primary-monitor origin.
        for device_id, device_outputs in enumerate(self.module.__dict__["__factory"].outputs):
            for output_id, output in enumerate(device_outputs):
                output.update_desc()
                if not output.attached_to_desktop:
                    continue
                r = output.desc.DesktopCoordinates
                desktop = (r.left, r.top, r.right, r.bottom)
                overlap = intersect(rect, desktop)
                if overlap is None:
                    continue
                key = (device_id, output_id)
                camera = self.cameras.get(key)
                if camera is None:
                    camera = self.module.create(device_idx=device_id, output_idx=output_id,
                        output_color="RGB", backend="dxgi", processor_backend="numpy")
                    self.cameras[key] = camera
                x1, y1, x2, y2 = overlap
                local = (x1-r.left, y1-r.top, x2-r.left, y2-r.top)
                frame = camera.grab(region=local, copy=False, new_frame_only=False)
                if frame is None:
                    previous = self.last_regions.get(key)
                    if previous is None or intersect(previous[0],local) != local:
                        raise FrameNotReady("Waiting for a fresh frame after ROI switch")
                    old,owned = previous
                    sample = owned.crop((local[0]-old[0],local[1]-old[1],local[2]-old[0],local[3]-old[1]))
                else:
                    if frame.shape[:2] != (y2-y1, x2-x1):
                        raise RuntimeError("Display geometry changed")
                    sample = Image.fromarray(frame).copy()
                    self.last_regions[key] = (local,sample)
                client.paste(sample, (x1-left, y1-top))
                covered += (x2-x1)*(y2-y1)
                outputs.append({"device": device_id, "output": output_id, "desktop_rect": desktop,
                                "roi_size": sample.size})
        if covered != (right-left)*(bottom-top):
            raise RuntimeError("Capture rectangle is outside the desktop")
        return client, {"backend": "DXGI Desktop Duplication", "strategy": "region_only",
                        "outputs": outputs}

    def close(self):
        for camera in self.cameras.values():
            try:
                camera.release()
            except Exception:
                pass
        self.cameras.clear()
        self.last_regions.clear()
