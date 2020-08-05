"""Tests for turbopy/computetools.py"""
import pytest
from turbopy.computetools import *


@pytest.fixture
def interpolator():
    """Pytest fixture for basic Interpolator class"""
    return Interpolators(Simulation({}), {"type": "Interpolator"})


def test_interpolate1D(interpolator):
    """Tests for turbopy.computetools.Interpolator's interpolate1D method"""
    x = np.arange(0, 10, 1)
    y = np.exp(x)
    xnew = np.arange(0, 1, 0.1)

    f1 = interpolator.interpolate1D(x, y)
    f2 = interpolate.interp1d(x, y)
    assert np.allclose(f1(x), y)
    assert np.allclose(f1(xnew), f2(xnew))

    y = np.asarray([n ** 2 for n in x])
    f1 = interpolator.interpolate1D(x, y, 'quadratic')
    f2 = interpolate.interp1d(x, y, 'quadratic')
    assert np.allclose(f1(x), y)
    assert np.allclose(f1(xnew), f2(xnew))


@pytest.fixture
def fin_diff():
    """Pytest fixture for basic FiniteDifference class with centered method."""
    dic = {"Grid": {"N": 10, "r_min": 0, "r_max": 10},
           "Clock": {"start_time": 0,
                     "end_time": 10,
                     "num_steps": 100},
           "Tools": {},
           "PhysicsModules": {},
           }
    sim = Simulation(dic)
    sim.run()
    return FiniteDifference(sim, {'type': 'FiniteDifference', 'method': 'centered'})


def test_setup_ddx(fin_diff):
    """Tests that `setup_ddx` returns the function specified by `method` in
    `input_data`.
    """
    y = np.arange(0, 10)
    center = fin_diff.setup_ddx()

    assert center == fin_diff.centered_difference
    assert center(y).shape == (10,)
    assert np.allclose(center(y), fin_diff.centered_difference(y))

    fin_diff.input_data['method'] = 'upwind_left'
    upwind = fin_diff.setup_ddx()
    assert upwind == fin_diff.upwind_left
    assert upwind(y).shape == (10,)
    assert np.allclose(upwind(y), fin_diff.upwind_left(y))


def test_centered_difference(fin_diff):
    """Tests for turbopy.computetools.FiniteDifference's centered_difference method."""
    dr = fin_diff.owner.grid.dr
    f = fin_diff.owner.grid.generate_field()
    y = np.arange(0, 10)

    assert np.allclose(fin_diff.centered_difference(y),
                       np.append([f[0]], np.append((y[2:] - y[:-2]) / (2 * dr), f[-1])))


def test_upwind_left(fin_diff):
    """Tests for turbopy.computetools.FiniteDifference's upwind_left method."""
    cell_widths = fin_diff.owner.grid.cell_widths
    f = fin_diff.owner.grid.generate_field()
    y = np.arange(0, 10)

    assert np.allclose(fin_diff.upwind_left(y), np.append([f[0]], (y[1:] - y[:-1]) / cell_widths))


def test_ddx(fin_diff):
    """Tests for turbopy.computetools.FiniteDifference's ddx method."""
    N = fin_diff.owner.grid.num_points
    g = 1 / (2.0 * fin_diff.dr)
    d = fin_diff.ddx()
    assert d.shape == (N, N)
    assert np.allclose(d.toarray(), sparse.dia_matrix(([np.zeros(N) - g, np.zeros(N) + g], [-1, 1]),
                                                      shape=(N, N)).toarray())


def test_radial_curl(fin_diff):
    """Tests for turbopy.computetools.FiniteDifference's radial_curl method."""
    with np.errstate(divide='ignore'):
        N = fin_diff.owner.grid.num_points
        dr = fin_diff.owner.grid.dr
        r = fin_diff.owner.grid.r
        g = 1 / (2.0 * dr)
        below = np.append(-g * (r[:-1] / r[1:])[:-1], [0.0, 0.0])
        diag = np.append(np.zeros(N - 1), [1 / dr])
        above = np.append([0.0, 2.0 / dr], g * (r[1:] / r[:-1])[1:])
        d = fin_diff.radial_curl()
        assert d.shape == (N, N)
        for actual, expected in zip(d.data, [below, diag, above]):
            assert np.allclose(actual, expected)


def test_del2_radial(fin_diff):
    """Tests for turbopy.computetools.FiniteDifference's del2_radial method."""
    with np.errstate(divide='ignore'):
        N = fin_diff.owner.grid.num_points
        dr = fin_diff.owner.grid.dr
        r = fin_diff.owner.grid.r
        g1 = 1 / (2.0 * dr)
        g2 = 1 / (dr ** 2)
        below = np.append(-g1 / r[1:], [-g1]) + (g2 * np.ones(N))
        above = (np.append([g1, 0], g1 / r[1:-1]) +
                 np.append([g2, g2 * 2], g2 * np.ones(N - 2)))
        diag = -2 * g2 * np.ones(N)
        d = fin_diff.del2_radial()
        d_array = d.toarray()
        assert d.shape == (N, N)
        for ind in range(N - 1):
            assert d_array[ind + 1][ind] == below[ind]
        for ind in range(N):
            assert d_array[ind][ind] == diag[ind]
        for ind in range(N - 1):
            assert d_array[ind][ind + 1] == above[ind + 1]


def test_del2(fin_diff):
    """Tests for turbopy.computetools.FiniteDifference's del2 method."""
    N = fin_diff.owner.grid.num_points
    dr = fin_diff.owner.grid.dr
    g = 1 / (dr ** 2)

    below = g * np.ones(N)
    diag = -2 * g * np.ones(N)
    above = g * np.ones(N)
    above[1] *= 2

    d = fin_diff.del2()
    assert d.shape == (N, N)
    for actual, expected in zip(d.data, [below, diag, above]):
        assert np.allclose(actual, expected)


def test_ddr(fin_diff):
    """Tests for turbopy.computetools.FiniteDifference's ddr method."""
    N = fin_diff.owner.grid.num_points
    dr = fin_diff.owner.grid.dr
    g1 = 1 / (2.0 * dr)

    below = -g1 * np.ones(N)
    above = g1 * np.ones(N)
    above[1] = 0

    d = fin_diff.ddr()
    assert d.shape == (N, N)
    for actual, expected in zip(d.data, [below, above]):
        assert np.allclose(actual, expected)


def test_BC_left_extrap(fin_diff):
    """Tests for turbopy.computetools.FiniteDifference's BC_left_extrap method."""
    N = fin_diff.owner.grid.num_points

    diag = np.append(0, np.ones(N-1))
    above = np.append([0.0, 2.0], np.zeros(N-2))
    above2 = np.append([0.0, 0.0, -1.0], np.zeros(N-3))

    d = fin_diff.BC_left_extrap()
    assert d.shape == (N, N)
    for actual, expected in zip(d.data, [diag, above, above2]):
        assert np.allclose(actual, expected)


def test_BC_left_avg(fin_diff):
    """Tests for turbopy.computetools.FiniteDifference's BC_left_avg method."""
    N = fin_diff.owner.grid.num_points

    diag = np.append(0, np.ones(N - 1))
    above = np.append([0.0, 1.5], np.zeros(N - 2))
    above2 = np.append([0.0, 0.0, -0.5], np.zeros(N - 3))

    d = fin_diff.BC_left_avg()
    assert d.shape == (N, N)
    for actual, expected in zip(d.data, [diag, above, above2]):
        assert np.allclose(actual, expected)


def test_BC_left_quad(fin_diff):
    """Tests for turbopy.computetools.FiniteDifference's BC_left_quad method."""
    N = fin_diff.owner.grid.num_points
    r = fin_diff.owner.grid.r
    R = (r[1]**2 + r[2]**2)/(r[2]**2 - r[1]**2)/2

    diag = np.append(0, np.ones(N - 1))
    above = np.append([0.0, 0.5 + R], np.zeros(N - 2))
    above2 = np.append([0.0, 0.0, 0.5 - R], np.zeros(N - 3))

    d = fin_diff.BC_left_quad()
    assert d.shape == (N, N)
    for actual, expected in zip(d.data, [diag, above, above2]):
        assert np.allclose(actual, expected)


def test_BC_left_flat(fin_diff):
    """Tests for turbopy.computetools.FiniteDifference's BC_left_flat method."""
    N = fin_diff.owner.grid.num_points

    diag = np.append(0, np.ones(N - 1))
    above = np.append([0.0, 1], np.zeros(N - 2))

    d = fin_diff.BC_left_flat()
    assert d.shape == (N, N)
    for actual, expected in zip(d.data, [diag, above]):
        assert np.allclose(actual, expected)


def test_BC_right_extrap(fin_diff):
    """Tests for turbopy.computetools.FiniteDifference's BC_right_extrap method."""
    N = fin_diff.owner.grid.num_points

    below2 = np.append(np.zeros(N - 3), [-1.0, 0.0, 0.0])
    below = np.append(np.zeros(N - 2), [2.0, 0.0])
    diag = np.append(np.ones(N - 1), 0)

    d = fin_diff.BC_right_extrap()
    assert d.shape == (N, N)
    for actual, expected in zip(d.data, [below2, below, diag]):
        assert np.allclose(actual, expected)
