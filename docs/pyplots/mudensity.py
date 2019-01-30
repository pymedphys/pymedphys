from pymedphys.mudensity import calc_mu_density, get_grid, display_mu_density

leaf_pair_widths = (5, 5, 5)
max_leaf_gap = 10

mu = [0, 2, 5, 10]
mlc = [
    [
        [1, 1],
        [2, 2],
        [3, 3]],
    [
        [2, 2],
        [3, 3],
        [4, 4]],
    [
        [-2, 3],
        [-2, 4],
        [-2, 5]],
    [
        [0, 0],
        [0, 0],
        [0, 0]]]

jaw = [
    [7.5, 7.5],
    [7.5, 7.5],
    [-2, 7.5],
    [0, 0]
]

grid = get_grid(max_leaf_gap=max_leaf_gap, leaf_pair_widths=leaf_pair_widths)

mu_density = calc_mu_density(
    mu, mlc, jaw, max_leaf_gap=max_leaf_gap, leaf_pair_widths=leaf_pair_widths)

display_mu_density(grid, mu_density)
