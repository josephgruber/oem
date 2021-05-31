import numpy as np
import warnings

from oem.tools import epoch_span_overlap, epoch_span_contains, time_range


REFERENCE_FRAMES = {
    "inertial": ["EME2000", "GCRF", "ICRF", "MCI", "TEME", "TOD"],
    "rotating": ["GRC", "ITRF2000", "ITRF-93", "ITRF-97", "TDR"]
}


class SegmentCompare(object):
    """Comparison of two EphemerisSegment.

    Input segments must have identical reference frames and central bodies.
    All comparisons are calculated in the input segment reference frame.

    Rotating reference frames are not supported for velocity-based or
    RIC comparisons.

    Attributes:
        is_empty (bool): Flag indicating overlap between compared segments. Set
            to True if there is no overlap.
    """

    def __init__(self, origin, target):
        """Create a SegmentCompare.

        Args:
            origin (EphemerisSegment): Segment at the origin of the
                compare frame.
            target (EphemerisSegment): Segment to compare against the
                origin state.
        """
        if (origin.metadata["REF_FRAME"] == target.metadata["REF_FRAME"]
                and origin.metadata["CENTER_NAME"]
                == target.metadata["CENTER_NAME"]):
            self._span = epoch_span_overlap(origin.span, target.span)
            self._origin = origin
            self._target = target
        else:
            raise ValueError(
                "Incompatible states: frame or central body mismatch."
            )

    def __contains__(self, epoch):
        return (
            self._span is not None and epoch_span_contains(self._span, epoch)
        )

    def __call__(self, epoch):
        if epoch not in self:
            raise ValueError(f"Epoch {epoch} not contained in SegmentCompare.")
        return self._target(epoch) - self._origin(epoch)

    def steps(self, step_size):
        """Sample SegmentCompare at equal time intervals.

        This method returns a generator producing state compares at equal time
        intervals spanning the useable duration of the parent EphemerisSegment.

        Args:
            step_size (float): Sample step size in seconds.

        Yields:
            state_compare: Sampled StateCompare.
        """
        for epoch in time_range(*self._span, step_size):
            yield self(epoch)

    @property
    def is_empty(self):
        return self._span is None


class StateCompare(object):
    """Comparison of two Cartesian states.

    Input states must have identical epochs, reference frames, and central
    bodies. All comparisons are calculated in the input state reference frame.

    Rotating reference frames are not supported for velocity-based or
    RIC comparisons.

    Attributes:
        range (float): Absolute distance between the two states.
        range_rate (float): Absolute velocity between the two states.
        position (ndarray): Relative position vector in the input frame.
        velocity (ndarray): Relative velocity vector in the input frame.
        position_ric (ndarray): Relative position vector in the RIC frame.
        velocity_ric (ndarray): Relative velocity vector in the RIC frame.

    Examples:
        To compare two states, `origin` and `target`, either call the
        StateCompare initializer directly

        >>> compare = StateCompare(origin, target)

        or simply difference the two states

        >>> compare = origin - target
    """

    def __init__(self, origin, target):
        """Create a StateCompare.

        Args:
            origin (State): State at the origin of the compare frame.
            target (State): State to compare against the origin state.

        Raises:
            ValueError: Incompatible states: epoch, frame, or central
                body mismatch.
        """
        if (origin.epoch == target.epoch
                and origin.frame == target.frame
                and origin.center == target.center):
            self._origin = origin
            self._target = target
            if self._origin.frame.upper() in REFERENCE_FRAMES["inertial"]:
                self._inertial = True
            elif self._origin.frame.upper() in REFERENCE_FRAMES["rotating"]:
                self._inertial = False
            else:
                warnings.warn(
                    f"Nonstandard frame: '{self._origin.frame}'. "
                    "Assuming intertial. Override with ._inertial=False",
                    UserWarning
                )
                self._inertial = True
        else:
            raise ValueError(
                "Incompatible states: epoch, frame, or central body mismatch."
            )

    def _require_inertial(self):
        if not self._inertial:
            raise NotImplementedError(
                "Velocity compares not supported for non-inertial frames. "
                "To override, set ._inertial=True."
            )

    def _to_ric(self, vector):
        self._require_inertial()
        cross_track = np.cross(self._origin.position, self._origin.velocity)
        in_track = np.cross(cross_track, self._origin.position)
        R = np.array([
            self._origin.position/np.linalg.norm(self._origin.position),
            in_track/np.linalg.norm(in_track),
            cross_track/np.linalg.norm(cross_track)
        ])
        return R.dot(vector)

    @property
    def range(self):
        return np.linalg.norm(self._target.position - self._origin.position)

    @property
    def range_rate(self):
        self._require_inertial()
        return np.linalg.norm(self._target.velocity - self._origin.velocity)

    @property
    def position(self):
        return self._target.position - self._origin.position

    @property
    def velocity(self):
        self._require_inertial()
        return self._target.velocity - self._origin.velocity

    @property
    def position_ric(self):
        return self._to_ric(self.position)

    @property
    def velocity_ric(self):
        return self._to_ric(self.velocity)
