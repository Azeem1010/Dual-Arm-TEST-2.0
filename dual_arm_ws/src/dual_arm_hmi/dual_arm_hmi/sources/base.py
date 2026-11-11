"""What the interface needs from a data source."""
from abc import ABC, abstractmethod


class DataSource(ABC):
    @abstractmethod
    def snapshot(self):
        """The latest state as a model.state.Snapshot."""

    @abstractmethod
    def frame(self, camera, annotated):
        """The latest BGR image for a camera, or None when there is no current image."""

    @abstractmethod
    def invoke(self, action):
        """Send an operator action. Must not block."""

    @abstractmethod
    def select_mode(self, mode):
        """Choose the mode the next system start will use."""

    def close(self):
        """Release any connections when the window closes."""

    def set_cycles(self, cycles):
        """Transfer cycles for the next simulation start."""

    def cycles(self):
        return 1

    def scenarios(self):
        """Selectable demonstration states as (key, label); empty for live data."""
        return ()

    def scenario(self):
        return ''

    def set_scenario(self, key):
        raise NotImplementedError
