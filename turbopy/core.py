"""
Computational Physics Simulation Framework

Based on the structure of turboWAVE
"""

from pathlib import Path
from abc import ABC, abstractmethod
import numpy as np
import qtoml as toml


def construct_simulation_from_toml(filename: str) -> Simulation:
    """Construct a Simulation instance from a toml input file

    Parameters
    ----------
    filename : `str`
        The name of the file which contains the input specification, in
        `toml` format.

    Returns
    -------
    simulation_instance : `Simulation`
        An instance of the Simulation class, initialized using the data
        in the input file, which was converted into a python dictionary.
    """
    with open(input_data) as f:
        input_data = toml.load(f)

    return Simulation(input_data)


class Simulation:
    """
    This Class "owns" all the physics modules, compute tools, and diagnostics.
    It also coordinates them.  The main simulation loop is driven by an
    instance of this class.

    Based on the Simulation class in TurboWAVE
    """

    def __init__(self, input_data: dict):
        self.physics_modules = []
        self.compute_tools = []
        self.diagnostics = []

        self.grid = None
        self.clock = None
        self.units = None

        self.input_data = input_data

    def run(self):
        """
        Runs the simulation.
        """
        print("Simulation is initializing")
        self.prepare_simulation()
        print("Initialization complete")

        print("Simulation is started")
        while self.clock.is_running():
            self.fundamental_cycle()

        self.finalize_simulation()
        print("Simulation complete")

    def fundamental_cycle(self):
        """
        Executes each diagnostic and physics module and advances the clock.
        """
        for d in self.diagnostics:
            d.diagnose()
        for m in self.physics_modules:
            m.reset()
        for m in self.physics_modules:
            m.update()
        self.clock.advance()

    def prepare_simulation(self):
        """
        Prepares the simulation by reading the input and initializing
        physics modules and diagnostics.
        """
        print("Reading Grid...")
        self.read_grid_from_input()

        print("Reading Tools...")
        self.read_tools_from_input()

        print("Reading PhysicsModules...")
        self.read_modules_from_input()

        print("Reading Diagnostics...")
        self.read_diagnostics_from_input()

        print("Initializing Simulation Clock...")
        self.read_clock_from_input()

        print("Initializing Tools...")
        for t in self.compute_tools:
            t.initialize()

        print("Initializing PhysicsModules...")
        for m in self.physics_modules:
            m.exchange_resources()
        for m in self.physics_modules:
            m.initialize()

        print("Initializing Diagnostics...")
        for d in self.diagnostics:
            d.initialize()

    def finalize_simulation(self):
        """
        Close out the simulation. Runs the finalize() method
        for each diagnostic.
        """
        for d in self.diagnostics:
            d.finalize()

    def read_grid_from_input(self):
        self.grid = Grid(self.input_data["Grid"])

    def read_clock_from_input(self):
        self.clock = SimulationClock(self, self.input_data["Clock"])

    def read_tools_from_input(self):
        if "Tools" in self.input_data:
            for tool_name, params in self.input_data["Tools"].items():
                tool_class = ComputeTool.lookup(tool_name)
                params["type"] = tool_name
                # TODO: somehow make tool names unique, or prevent more than one each
                self.compute_tools.append(tool_class(owner=self, input_data=params))

    def read_modules_from_input(self):
        for physics_module_name, physics_module_data in self.input_data["PhysicsModules"].items():
            physics_module_class = PhysicsModule.lookup(physics_module_name)
            physics_module_data["name"] = physics_module_name
            self.physics_modules.append(physics_module_class(owner=self, input_data=physics_module_data))
        self.sort_modules()

    def read_diagnostics_from_input(self):
        if "Diagnostics" in self.input_data:
            # This dictionary has two types of keys:
            #    keys that are valid diagnostic types
            #    other keys, which should be passed along as "default" parameters
            diags = {k: v for k, v in self.input_data["Diagnostics"].items() if Diagnostic.is_valid_name(k)}
            params = {k: v for k, v in self.input_data["Diagnostics"].items() if not Diagnostic.is_valid_name(k)}

            # todo: implement a system for making default file names
            if "directory" in params:
                d = Path(params["directory"])
                d.mkdir(parents=True, exist_ok=True)

            for diag_type, d in diags.items():
                diagnostic_class = Diagnostic.lookup(diag_type)
                if not type(d) is list:
                    d = [d]
                for di in d:
                    # Values in di supersede values in params because of the order
                    di = {**params, **di, "type": diag_type}
                    if "directory" in di and "filename" in di:
                        di["filename"] = str(Path(di["directory"]) / Path(di["filename"]))
                    self.diagnostics.append(diagnostic_class(owner=self, input_data=di))

    def sort_modules(self):
        pass

    def find_tool_by_name(self, tool_name):
        tools = [t for t in self.compute_tools if t.name == tool_name]
        if len(tools) == 1:
            return tools[0]
        return None


class DynamicFactory(ABC):
    """
    This base class provides a dynamic factory pattern functionality to classes
    that derive from this.
    """
    @property
    @abstractmethod
    def _factory_type_name(self):
        pass

    @property
    @abstractmethod
    def _registry(self):
        pass

    @classmethod
    def register(cls, name_to_register, class_to_register):
        if name_to_register in cls._registry:
            raise ValueError("{0} '{1}' already registered".format(cls._factory_type_name, name_to_register))
        if not issubclass(class_to_register, cls):
            raise TypeError("{0} is not a subclass of {1}".format(class_to_register, cls))
        cls._registry[name_to_register] = class_to_register

    @classmethod
    def lookup(cls, name):
        try:
            return cls._registry[name]
        except KeyError:
            raise KeyError("{0} '{1}' not found in registry".format(cls._factory_type_name, name))

    @classmethod
    def is_valid_name(cls, name):
        return name in cls._registry


class PhysicsModule(DynamicFactory):
    """
    This is the base class for all physics modules
    Based on Module class in TurboWAVE

    Because python mutable/immutable is different than C++ pointers, the implementation 
    here is different. Here, a "resource" is a dictionary, and can have more than one 
    thing being shared. Note that the value stored in the dictionary needs to be mutable. 
    Make sure not to reinitialize, because other physics modules will be holding a reference to it.
    """
    _factory_type_name = "Physics Module"
    _registry = {}

    def __init__(self, owner: Simulation, input_data: dict):
        self.owner = owner
        self.module_type = None
        self.input_data = input_data

    def publish_resource(self, resource: dict):
        for physics_module in self.owner.physics_modules:
            physics_module.inspect_resource(resource)
        for diagnostic in self.owner.diagnostics:
            diagnostic.inspect_resource(resource)

    def inspect_resource(self, resource: dict):
        """
        If your subclass needs the data described by the key, now's their chance to 
        save a pointer to the data
        """
        pass

    def exchange_resources(self):
        """
        This is the function where you call publish_resource, to tell other physics modules 
        about data you want to share
        """
        pass

    def update(self):
        raise NotImplementedError

    def reset(self):
        pass

    def initialize(self):
        pass


class ComputeTool(DynamicFactory):
    """
    This is the base class for compute tools. These are the compute-heavy functions,
    which have implementations of numerical methods which can be shared between physics modules.
    """
    _factory_type_name = "Compute Tool"
    _registry = {}

    def __init__(self, owner: Simulation, input_data: dict):
        self.owner = owner
        self.input_data = input_data
        self.name = input_data["type"]

    def initialize(self):
        pass


class SimulationClock:
    def __init__(self, owner: Simulation, clock_data: dict):
        self.owner = owner
        self.start_time = clock_data["start_time"]
        self.time = self.start_time
        self.end_time = clock_data["end_time"]
        self.this_step = 0
        self.print_time = False
        if "print_time" in clock_data:
            self.print_time = clock_data["print_time"]

        if "num_steps" in clock_data:
            self.num_steps = clock_data["num_steps"]
            self.dt = ((clock_data["end_time"] - clock_data["start_time"]) /
                       clock_data["num_steps"])
        elif "dt" in clock_data:
            self.dt = clock_data["dt"]
            self.num_steps = (self.end_time - self.start_time) / self.dt
            if not np.isclose(self.num_steps, np.rint(self.num_steps)):
                raise (RuntimeError("Simulation interval is not an integer multiple of timestep dt"))
            self.num_steps = np.int(np.rint(self.num_steps))

    def advance(self):
        self.this_step += 1
        self.time = self.start_time + self.dt * self.this_step
        if self.print_time:
            print(f"t = {self.time}")

    def is_running(self):
        return self.this_step < self.num_steps


class Grid:
    def __init__(self, grid_data: dict):
        self.grid_data = grid_data
        self.r_min = None
        self.r_max = None
        self.num_points = None
        self.dr = None
        self.parse_grid_data()

        self.r = self.r_min + (self.r_max - self.r_min) * self.generate_linear()
        self.cell_edges = self.r
        self.cell_centers = (self.r[1:] + self.r[:-1]) / 2
        self.cell_widths = (self.r[1:] - self.r[:-1])
        # This will give a divide-by-zero warning. I'm ok with that for now.
        self.r_inv = 1 / self.r
        self.r_inv[0] = 0

    def parse_grid_data(self):
        self.set_value_from_keys("r_min", {"min", "x_min", "r_min"})
        self.set_value_from_keys("r_max", {"max", "x_max", "r_max"})
        if "N" in self.grid_data:
            self.num_points = self.grid_data["N"]
            self.dr = (self.r_max - self.r_min) / (self.num_points - 1)
        else:
            self.set_value_from_keys("dr", {"dr", "dx"})
            self.num_points = 1 + (self.r_max - self.r_min) / self.dr
            if not (self.num_points % 1 == 0):
                raise (RuntimeError("Invalid grid spacing: configuration does not imply integer number of grid points"))
            self.num_points = np.int(self.num_points)

    def set_value_from_keys(self, var_name, options):
        for name in options:
            if name in self.grid_data:
                setattr(self, var_name, self.grid_data[name])
                return
        raise (KeyError("Grid configuration for " + var_name + " not found."))

    def generate_field(self, num_components=1):
        return np.squeeze(np.zeros((self.num_points, num_components)))

    def generate_linear(self):
        return np.linspace(0, 1, self.num_points)

    def create_interpolator(self, r0):
        # Return a function which linearly interpolates any field on this grid, to the point x
        assert (r0 >= self.r_min), "Requested point is not in the grid"
        assert (r0 <= self.r_max), "Requested point is not in the grid"
        i, = np.where((r0 - self.dr < self.r) & (self.r < r0 + self.dr))
        assert (len(i) in [1, 2]), "Error finding requested point in the grid"
        if len(i) == 1:
            return lambda y: y[i]
        if len(i) == 2:
            # linearly interpolate
            def interpval(yvec):
                rvals = self.r[i]
                y = yvec[i]
                return y[0] + (r0 - rvals[0]) * (y[1] - y[0]) / (rvals[1] - rvals[0])

            return interpval


class Diagnostic(DynamicFactory):
    _factory_type_name = "Diagnostic"
    _registry = {}

    def __init__(self, owner: Simulation, input_data: dict):
        self.owner = owner
        self.input_data = input_data

    def inspect_resource(self, resource: dict):
        """
        If your subclass needs the data described by the key, now's their chance to 
        save a pointer to the data
        """
        pass

    def diagnose(self):
        raise NotImplementedError

    def initialize(self):
        pass

    def finalize(self):
        pass
