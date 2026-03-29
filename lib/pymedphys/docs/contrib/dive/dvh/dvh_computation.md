# Analytical DVH computation for PyMedPhys

Resolving structure-boundary and dose-threshold discontinuities without geometric supersampling.

## Scope

This document assumes that RT structure contours are defined on parallel axial planes of constant patient $z$, derived from standard CT image slices with uniform or near-uniform slice spacing. This covers the vast majority of clinical RTSTRUCT data. DICOM does permit contours on non-axial or non-parallel planes, but those cases are outside the scope of the current engine.

## The integral a cumulative DVH represents

A dose-volume histogram is, at its core, a single integral. You have two continuous 3D fields overlaid on the same patient geometry:

- A **dose field** $D(\mathbf{r})$, defined everywhere in the patient by the treatment planning system (TPS). It is stored on a grid but represents a continuous physical quantity (energy deposited per unit mass).
- A **structure occupancy field** $\Omega(\mathbf{r})$, which is 1 inside the structure and 0 outside. Equivalently, this is the indicator function $\mathbf{1}[\mathbf{r} \in S]$.

The cumulative DVH at dose level $d$ is:

$$V(d) = \int_{\mathbb{R}^3} \Omega(\mathbf{r}) \cdot \mathbf{1}[D(\mathbf{r}) \geq d] \, d^3r$$

and the total structure volume is:

$$V_S = \int_{\mathbb{R}^3} \Omega(\mathbf{r}) \, d^3r$$

Every DVH algorithm, from the simplest binary centre-point test to the most sophisticated commercial implementation, is an approximation to this integral. The differences between algorithms are entirely differences in **how they discretise and evaluate** it.

Notice that this integral contains **two** discontinuities:

1. The structure indicator $\Omega(\mathbf{r})$, which jumps at the structure boundary.
2. The dose threshold indicator $\mathbf{1}[D \geq d]$, which jumps at the isodose surface $D(\mathbf{r}) = d$.

The SDF resolves the first. The second requires separate treatment. A complete DVH algorithm must handle both.

## The two fields have different character

### The dose field is smooth

The dose $D(\mathbf{r})$ is computed by the TPS on a grid (typically 2.0--2.5 mm for conventional EBRT, 1.0--1.25 mm for SRS). Between grid points, the dose varies smoothly. Even at the sharpest field edges, the physical penumbra (set by lateral electron transport) provides a typical transition width of approximately 5--8 mm for conventional 6 MV photon fields [^14] (ch. 13), though narrower penumbrae occur in small-field and stereotactic contexts. The dose can be reconstructed between grid points via trilinear interpolation:

$$D(\mathbf{r}) = \sum_{i,j,k} D_{ijk} \cdot L_i(x) \cdot L_j(y) \cdot L_k(z)$$

where $L_i$ are linear basis functions (hat functions). This is a continuous, piecewise-trilinear field, smooth within each interpolation cell and $C^0$ across cell boundaries. Note that the choice of interpolation model is an implementation decision. DICOM RT Dose does not mandate a particular off-grid interpolation scheme [^15] (C.8.8.3). Trilinear interpolation is the most common and natural choice.

### Interpolation cells versus sample-centred voxels

An important distinction must be made between two ways of tiling space from a dose grid.

**Sample-centred voxels.** DICOM Image Position (Patient) defines the centre of the first transmitted pixel [^15]. Each stored dose value $D_{ijk}$ is associated with a spatial position, and the "voxel" is the region of space closer to that grid point than to any neighbour, extending $\pm \Delta x / 2$ in each axis.

**Interpolation cells.** The trilinear interpolation function is defined on cells bounded by eight adjacent grid points. Within each such cell, the eight corner values uniquely determine the trilinear interpolant.

These two tilings are offset by half a grid spacing. A sample-centred voxel straddles parts of $2^3 = 8$ interpolation cells; an interpolation cell straddles parts of $2^3 = 8$ sample-centred voxels.

**This engine uses interpolation cells as its computational tiling.** The reason is that the trilinear dose model is naturally defined on interpolation cells, and key properties (such as the extrema occurring at the eight corners; see below) hold exactly for interpolation cells but not for sample-centred voxels.

A consequence is that the outermost ring of grid points defines cells that extend only inward, so the outermost half-voxel layer of the dose grid has no interpolation cell. For most clinical geometries, structures of interest are well within the dose grid and this boundary layer is irrelevant. **The default behaviour of this engine is to treat the RT Dose support as finite and explicit.** If a queried structure intersects the unsupported boundary region, a warning is emitted. An optional named extension mode can extrapolate the outermost grid values by one half-spacing to create boundary cells, but this is a modelling choice (not implied by DICOM) and is disabled by default.

### The structure occupancy is discontinuous

The structure $S$ has a sharp boundary. $\Omega(\mathbf{r})$ jumps from 0 to 1 at the surface $\partial S$. When you discretise the integral on a grid, cells that straddle this boundary can be anywhere from 0% to 100% inside the structure. Getting this fraction wrong, which the naive binary method does catastrophically, is a major source of DVH error.

### The SDF makes the geometric discontinuity analytically tractable

A signed distance field $\phi(\mathbf{r})$ is a continuous scalar field that encodes the structure boundary implicitly:

$$
\phi(\mathbf{r}) = \begin{cases}
-d(\mathbf{r}, \partial S) & \text{if } \mathbf{r} \in S \\
+d(\mathbf{r}, \partial S) & \text{if } \mathbf{r} \notin S
\end{cases}
$$

The boundary is the zero level set: $\partial S = \lbrace\mathbf{r} : \phi(\mathbf{r}) = 0\rbrace$. The occupancy function is $\Omega(\mathbf{r}) = \mathbf{1}[\phi(\mathbf{r}) < 0]$.

Although $\Omega$ is discontinuous, $\phi$ is continuous and carries rich geometric information: the **exact distance** to the boundary, the **surface normal** $\hat{\mathbf{n}} = \nabla\phi / |\nabla\phi|$, and the **surface curvature** (from the Hessian of $\phi$). This is precisely the information needed to compute the volume of the cell-structure intersection analytically, without brute-force subdivision.

## How the naive method discretises the integral

The standard raster-mask approach approximates the DVH integral by building a binary occupancy mask on dose-grid planes and histogramming the masked dose values. Implementations such as dicompyler-core [^19] construct 2D contour masks at each dose-grid $z$-plane, apply XOR logic for holes, and accumulate dose samples from the masked points plane by plane. This is a raster-mask family of methods. At its simplest, it reduces to a centre-point quadrature rule:

$$V(d) \approx \sum_{i,j,k} \Delta V \cdot \mathbf{1}[\mathbf{r}_c \in S] \cdot \mathbf{1}[D_{ijk} \geq d]$$

where $\mathbf{r}_c$ is the voxel centre. This is a centre-point quadrature rule applied to both the geometry and the dose simultaneously. It is exact if both $\Omega$ and $D$ are constant within each voxel, which is approximately true for $D$ (smooth field) but catastrophically wrong for $\Omega$ (discontinuous at the boundary).

For each boundary voxel, the method makes a binary decision: is the centre inside or outside? A voxel that is 99% inside gets $v = \Delta V$; one that is 49% inside gets $v = 0$. The maximum error per boundary voxel is $\pm \Delta V$.

For a roughly spherical structure of radius $R$ on a grid with spacing $\Delta x$, the number of boundary voxels scales as:

$$N_{\text{boundary}} \sim \frac{4\pi R^2}{\Delta x^2}$$

For a 5 cm radius sphere on a 2.5 mm grid, that is roughly 5,000 boundary voxels, each with a potential error of up to $\Delta V$.

## Supersampling as brute force

Supersampling subdivides each voxel into $k \times k \times k$ sub-voxels:

$$v_{ijk} \approx \frac{\Delta V}{k^3} \sum_{a=1}^{k} \sum_{b=1}^{k} \sum_{c=1}^{k} \mathbf{1}[(x_a, y_b, z_c) \in S]$$

At $k = 4$, you get 64 samples per boundary voxel with a volume fraction quantisation step of $1/64 \approx 1.6\%$. But convergence of the boundary volume error is only $O(1/k)$, because a finer binary mask is still a binary mask: the staircase boundary approximation improves only linearly with $k$.

The quantisation step $1/k^3$ and the boundary convergence rate $O(1/k)$ are different quantities and should not be conflated. At $k = 10$, the sub-voxel volume quantum is $1/1000 = 0.1\%$, but the per-voxel boundary error converges only as $O(1/k)$, with geometry-dependent constants. In the simplest 1D midpoint-sampling analogue, the mean fractional boundary error is $1/(4k)$ and the worst case is $1/(2k)$. In 3D the constants depend on surface orientation relative to the grid, but the $O(1/k)$ rate is fundamental: the exact boundary position, known analytically from the contour vertices, is never used by the supersampling approach.

## The SDF approach

### Step 1: Compute the SDF directly from contour geometry

Your DICOM RT Structure Set contains polygon vertices with sub-millimetre precision. Each contour edge defines the exact boundary position at that slice height. Rather than rasterising these polygons to a binary mask (destroying sub-voxel information), compute the **exact signed distance** from each dose grid point to the nearest polygon edge.

For each edge from $\mathbf{v}_m$ to $\mathbf{v}_{m+1}$ and query point $\mathbf{p}$:

$$\mathbf{e} = \mathbf{v}_{m+1} - \mathbf{v}_m$$

$$t = \operatorname{clamp}\!\left(\frac{(\mathbf{p} - \mathbf{v}_m) \cdot \mathbf{e}}{\mathbf{e} \cdot \mathbf{e}},\; 0,\; 1\right)$$

$$d_m = \left\lVert \mathbf{p} - \left(\mathbf{v}_m + t\,\mathbf{e}\right) \right\rVert$$

$$\phi(\mathbf{p}) = s(\mathbf{p}) \cdot \min_{m} d_m$$

where $s(\mathbf{p}) = -1$ if $\mathbf{p}$ is inside the polygon (determined by the crossing-number or winding-number test) and $s(\mathbf{p}) = +1$ otherwise.

**At each contour slice, this 2D signed distance computation is exact relative to the encoded polygon boundary**, to floating-point precision. The signed distance from each grid point to the polygon as transmitted in the RTSTRUCT is computed directly from the analytic vertex geometry. No rasterisation, no information loss. However, the polygon itself is only an approximation to the intended smooth anatomy (see the section on contour vertex fidelity below). The full 3D structure model, which depends on the inter-slice interpolation chosen in Step 2, is a further modelling choice rather than an exact geometric quantity.

#### Contour vertex fidelity

The 2D SDF is exact with respect to the polygon as encoded in the RTSTRUCT, but the polygon itself is an approximation to the smooth anatomical boundary. When a circular or curved contour of radius $r$ is represented by chords of length $h$, the radial sagitta error (the maximum inward deviation of the chord from the true arc) is approximately:

$$\epsilon_{\text{sag}} \approx \frac{h^2}{8r}$$

To keep the radial error below a tolerance $\epsilon$, the maximum allowable chord length is $h \leq \sqrt{8 r \epsilon}$.

For small SRS targets, vertex sparsity can dominate the total DVH error, even before any dose-grid or clipping approximation enters. Consider a 3 mm diameter sphere (slice radius $r = 1.5$ mm at the equator). An inscribed regular polygon with $n$ vertices underestimates the enclosed area by a factor $1 - (n / (2\pi)) \sin(2\pi / n)$:

| Vertices ($n$) | Area underestimate |
| --- | --- |
| 8 | ~10.0% |
| 16 | ~2.6% |
| 24 | ~1.1% |
| 32 | ~0.6% |

Real exported contours can be worse than the regular-polygon case because point spacing is often uneven, and TPS contour export routines may apply decimation that further reduces vertex count.

No downstream DVH algorithm can reconstruct curvature that was never present in the RTSTRUCT polygon. For a reference-quality DVH calculator, contour vertex fidelity is an **input-data quality concern** that must be assessed before the DVH computation begins. Recommended QA checks include:

- **Minimum vertex count per contour:** flag contours with fewer than 16 vertices for structures with expected radius below 5 mm.
- **Maximum chord length:** flag any chord exceeding $\sqrt{8 r_{\text{expected}} \epsilon_{\text{tol}}}$ for the declared structure type.
- **Area deficit estimate:** for approximately circular slices, compare the polygon area to $\pi r^2$ where $r$ is estimated from the polygon's bounding circle.

These checks should be reported as input-data quality warnings, separate from the DVH computation accuracy itself.

#### A note on DICOM contour semantics

Before computing the SDF, contour polygons must be normalised into correct polygon topology. DICOM allows at least two techniques for representing inner excluded regions: the **keyhole** technique (a narrow connecting channel between outer and inner contours) and **CLOSEDPLANAR_XOR** (contours on the same slice combined by repeated exclusive disjunction). The standard states that points along the keyhole connecting channel are considered inside the ROI [^15] (C.8.8.6.3). Additionally, if any contour in an ROI uses the `CLOSEDPLANAR_XOR` geometric type, then all contours in that ROI shall be of that type [^15] (C.8.8.6.3). This constraint matters for input validation: a structure set containing a mix of `CLOSEDPLANAR_XOR` and other types within a single ROI is malformed, not merely complex. Any implementation that applies inside-outside tests to each contour independently will mishandle these cases. A robust pipeline must parse and normalise the contour topology before computing signed distances.

#### The computation is fully vectorisable

For a dose grid slice with $M = M_x \times M_y$ points and a contour with $N$ edges:

```python
# points: shape (M, 2)
# v0, v1: shape (N, 2) -- edge start/end vertices

# Broadcast: (M, 1, 2) - (1, N, 2) -> (M, N, 2)
dp = points[:, None, :] - v0[None, :, :]
edges = v1 - v0

# Parameter along each edge, clamped to [0, 1]
t = np.clip(np.sum(dp * edges, axis=-1) / np.sum(edges * edges, axis=-1), 0, 1)

# Distance to nearest point on each edge
nearest = v0 + t[..., None] * edges
dist = np.linalg.norm(points[:, None, :] - nearest, axis=-1)  # (M, N)

# Minimum distance across all edges -> unsigned distance
min_dist = np.min(dist, axis=1)  # (M,)
```

For $M = 65\,536$ grid points and $N = 100$ edges, this is 6.5 million point-to-segment distances. Provisional estimates suggest completion in order 10 ms in NumPy or under 1 ms on GPU, though these figures should be benchmarked for specific hardware and use cases.

### Step 2: Extend to 3D via inter-slice interpolation

RT contours exist on discrete CT slices at heights $z_0, z_1, \ldots, z_K$. Between slices, DICOM provides no geometry. The 3D structure must be reconstructed, and that reconstruction is a **modelling choice**, not a uniquely determined answer. Published work on contour interpolation shows that branching, rapid area changes, and contour correspondence are all non-trivial [^8].

Our chosen reconstruction model: compute the 2D SDF at each contour slice, then linearly interpolate for dose grid points between slices:

$$\phi(x, y, z) = (1 - \alpha)\,\phi(x, y;\, z_k) + \alpha\,\phi(x, y;\, z_{k+1})$$

where $\alpha = (z - z_k) / (z_{k+1} - z_k)$.

The zero level set of this interpolated field defines a continuous implicit surface that morphs between contour shapes. This is the chosen reconstruction model. It is not an approximation to some other "true" surface (none exists in DICOM); it is the geometric model we adopt for DVH computation. This model sidesteps the need for explicit contour correspondence by adopting a particular implicit interpolation; it does not solve the contour-correspondence problem in any absolute sense. Topology changes (a structure splitting into two lobes) are permitted by the model without explicit correspondence logic, but the resulting between-slice geometry is a mathematical interpolation, not necessarily an anatomically faithful reconstruction.

#### Handling z-axis misalignment between dose and contour grids

In general, the dose grid $z$-positions will not coincide with the contour slice $z$-positions. CT slices might be spaced at 2.5 mm starting at $z = 0.0$ mm, while the dose grid might be at 2.5 mm spacing starting at $z = 1.2$ mm. The interpolation formula above handles this naturally: for each dose grid $z$-plane, find the two bracketing contour slices ($z_k \leq z < z_{k+1}$) and interpolate. The 2D SDFs at the contour slice heights are pre-computed on the in-plane $(x, y)$ coordinates of the dose grid, so the interpolation parameter $\alpha$ is the only quantity that depends on $z$-alignment.

If the dose grid extends beyond the contour stack in $z$ (i.e. the dose grid has planes above the superior contour or below the inferior contour), those planes are handled by the end-cap extrapolation described below. If the dose grid is coarser than the contour spacing in $z$ (dose slices skip over contour slices), intermediate contour slices are still used as interpolation anchors: for a dose plane at height $z$, only the immediately bracketing contour slices at $z_k$ and $z_{k+1}$ contribute, regardless of how many contour slices exist elsewhere.

An important caveat: this interpolated field is not, in general, the exact Euclidean distance to its own zero level set. It is a valid implicit representation of the structure (sign is correct, zero crossing is correct), but the magnitude of $\phi$ between contour planes may deviate from true Euclidean distance. In particular, the interpolated field is not guaranteed to be 1-Lipschitz: the $z$-derivative $\partial\phi/\partial z$ equals $(\phi_{k+1} - \phi_k)/(z_{k+1} - z_k)$, which can exceed 1 in magnitude. This means $|\nabla\phi|$ can exceed 1, and the field may overestimate distance in some directions.

Consequently, the half-diagonal classification test ($|\phi(\mathbf{c}_Q)| > \ell$ implies fully inside or outside) is **not rigorously guaranteed** for the interpolated field. A cell classified as "fully interior" could, in principle, be clipped by the true zero level set. Two options exist:

1. **Reinitialise** the interpolated field to an approximate Euclidean SDF via fast marching (`skfmm.distance`), which solves $|\nabla\phi| = 1$ with the zero level set held fixed. After reinitialisation, the half-diagonal test becomes well-founded (though still subject to the $O(\Delta x)$ numerical error inherent in the fast marching discretisation, which is typically much smaller than the half-diagonal margin for clinically relevant grids).
2. **Use sign-only classification** (safe under trilinear interpolation of $\phi$): classify a cell as interior only if $\phi < 0$ at all 8 corners, exterior only if $\phi > 0$ at all 8 corners, and boundary otherwise. This is safe because trilinear interpolation is sign-preserving: if all eight corner values share a sign, the trilinear interpolant shares that sign everywhere in the cell. This avoids any distance-magnitude assumption but classifies more cells as "boundary" than necessary.

For a production engine, option 1 is recommended. The reinitialisation cost is $O(N \log N)$ via fast marching on the 3D grid and needs to be done only once per structure.

**End-capping** also emerges from this framework. Beyond the topmost contour at $z_K$, extrapolate with a distance penalty:

$$\phi(x, y, z) = \phi(x, y;\, z_K) + (z - z_K) \quad \text{for } z > z_K$$

The increasing positive offset causes the zero level set to contract inward and close. The symmetrically decreasing case applies at the inferior end. This is one of several possible end-cap models; the choice should be documented and, ideally, configurable.

### Step 3: Classify cells and compute the in-structure region

With $\phi(i,j,k)$ at every dose grid point, classify interpolation cells. Define the cell half-diagonal:

$$\ell = \tfrac{1}{2}\sqrt{\Delta x^2 + \Delta y^2 + \Delta z^2}$$

Two classification strategies are available, depending on whether the SDF has been reinitialised:

**After reinitialisation (distance-based classification):**

- **Fully interior**: $\phi(\mathbf{c}_Q) < -\ell$ at the cell centre. Set $f = 1$.
- **Fully exterior**: $\phi(\mathbf{c}_Q) > +\ell$ at the cell centre. Set $f = 0$.
- **Boundary**: $|\phi(\mathbf{c}_Q)| \leq \ell$. The structure surface may intersect the cell. Compute $f$ analytically.

Note: for a reinitialised field that is approximately 1-Lipschitz, the centre-distance test $\phi(\mathbf{c}_Q) < -\ell$ implies $\phi < 0$ at all 8 corners (since each corner is within distance $\ell$ of the centre). The converse does not hold: all corners having $\phi < 0$ does not imply $\phi(\mathbf{c}_Q) < -\ell$. These are different criteria with different degrees of conservatism.

**Without reinitialisation (sign-only classification):**

- **Fully interior**: $\phi < 0$ at all 8 corners. Set $f = 1$.
- **Fully exterior**: $\phi > 0$ at all 8 corners. Set $f = 0$.
- **Boundary**: mixed signs at the corners. Compute $f$ analytically.

This is more conservative (classifies more cells as boundary) but requires no distance-magnitude assumption.

For boundary cells, the SDF provides the signed distance from the cell centre to the boundary, plus the surface normal $\hat{\mathbf{n}} = \nabla\phi / |\nabla\phi|$ via finite differences on the SDF grid. Under the **planar approximation** (the boundary within the cell is locally flat), the in-structure portion $P_Q = Q \cap S$ is a plane-clipped box. Its volume fraction has a closed-form expression given by the classical PLIC (piecewise linear interface calculation) relations [^1].

For the simplest case, with normal aligned to a grid axis (say $\hat{x}$):

$$f = \frac{1}{2} - \frac{\phi}{\Delta x}$$

This is exact for planar boundaries. For general normal directions, the formula is a piecewise polynomial in $\phi$ with breakpoints depending on $\hat{\mathbf{n}}$ and the cell dimensions. Analytic solutions for all cases are given by Lehmann and Gekle [^2].

## Accuracy of the planar approximation

The planar model assumes the structure boundary is flat within each cell. The error comes from **surface curvature**. If the surface has local radius of curvature $R$, the boundary deviates from the tangent plane by the sagitta:

$$\epsilon \sim \frac{\Delta x^2}{8R}$$

As a fractional volume error per boundary cell: $\epsilon_f \sim \Delta x / (8R)$.

| Structure | Typical $R$ | $\Delta x$ | $\Delta x / R$ | Planar error |
| --- | --- | --- | --- | --- |
| Bladder, liver | 50--100 mm | 2.5 mm | 0.025--0.05 | 0.3--0.6% per cell |
| Prostate, kidney | 20--40 mm | 2.5 mm | 0.06--0.13 | 0.8--1.6% per cell |
| Optic nerve | 3--5 mm | 1.0 mm | 0.2--0.33 | 2.5--4.2% per cell |
| 3 mm brain met | 1.5 mm | 1.0 mm | 0.67 | ~8% per cell |

For structures with $R / \Delta x > 5$, the planar model is expected to perform well. Higher curvature structures need corrections or exact clipping, derived below.

## The dose-threshold discontinuity

Up to this point, we have focused entirely on resolving the first discontinuity in the DVH integral: the structure boundary. Once the in-structure volume fraction $f$ is known for each boundary cell, the temptation is to assign a single "effective dose" $D_{\text{eff}}$ to the cell and threshold that:

$$V_Q(d) \approx \mathbf{1}[D_{\text{eff}} \geq d] \cdot |P_Q|$$

where $|P_Q| = f \cdot \Delta V$ is the in-structure volume. For mean dose calculations, using the centroid dose as $D_{\text{eff}}$ is exact under a linear dose model. But **a cumulative DVH is not a mean dose calculation**.

The DVH needs the volume above threshold $d$ within the in-structure portion of the cell:

$$V_Q(d) = \left| P_Q \cap \lbrace\mathbf{r} : D(\mathbf{r}) \geq d\rbrace \right|$$

That depends on the **distribution** of dose across $P_Q$, not just its mean.

### Why a single effective dose fails: a 1D counterexample

Consider a cell spanning $[0, 2.5]$ mm with the structure boundary at $x_b = 1.8$ mm and a linear dose field $D(x) = 60 + 4(x - 1.25)$ Gy (gradient of 4 Gy/mm).

The in-structure region is $[0, 1.8]$ mm. Its centroid is at $x = 0.9$ mm, where $D(0.9) = 58.6$ Gy. For the mean dose integral, the centroid correction is exact: $58.6 \times 1.8 = 105.48$ Gy-mm, which matches the true integral $\int_0^{1.8} D(x)\,dx = 105.48$ Gy-mm. So far, so good.

Now evaluate the cumulative DVH at threshold $d = 60$ Gy. Inside the structure, the dose exceeds 60 Gy only where $x \geq 1.25$. The exact in-structure length above 60 Gy is:

$$1.8 - 1.25 = 0.55 \text{ mm}$$

A single effective dose cannot reproduce this. Thresholding the centroid dose 58.6 Gy gives 0 mm above threshold (wrong). Thresholding the centre-point dose 60.0 Gy gives either the full 1.8 mm or 0 mm depending on how the tie is broken (also wrong). The true answer, 0.55 mm, requires knowing _where_ the isodose surface $D = d$ intersects the in-structure region.

### Which cells are affected?

The dose-threshold discontinuity affects any cell where the isodose surface $D(\mathbf{r}) = d$ passes through it, regardless of whether the cell is a structure-boundary cell, an interior cell, or (trivially) an exterior cell.

Under the trilinear dose model within an interpolation cell, the extrema of $D$ occur at the eight corners (the grid points). This follows because a trilinear function is linear along any axis when the other two coordinates are fixed, so it cannot have an interior extremum; its maximum and minimum over the cell always occur at vertices. Define:

$$D_{\min,Q} = \min(D_1, \ldots, D_8), \qquad D_{\max,Q} = \max(D_1, \ldots, D_8)$$

where $D_1, \ldots, D_8$ are the stored dose values at the eight grid points bounding the cell. Then for any threshold $d$:

- If $D_{\min,Q} \geq d$: the entire cell is above threshold.
- If $D_{\max,Q} < d$: the entire cell is below threshold.
- Otherwise: the cell is **dose-ambiguous** at threshold $d$, and the isodose surface passes through it.

This corner-based test is exact for the trilinear dose model on interpolation cells. It is a much better dispatch criterion than any gradient-based heuristic, because it uses actual dose values rather than a derivative estimate.

**Note:** This extrema property does not hold for sample-centred voxels. A sample-centred voxel (extending $\pm \Delta x / 2$ around a grid point) straddles multiple interpolation cells, and the trilinear interpolant can attain interior extrema within such a voxel. The choice of interpolation cells as the computational tiling (see above) is essential for the corner-dose dispatch to be valid.

There are therefore **three** categories of cell for DVH evaluation:

1. **Interior + dose-unambiguous** (the vast majority). The cell is fully inside the structure and all corner doses are above (or all below) the threshold. Contribution: $\Delta V$ or $0$. No clipping needed.

2. **Interior + dose-ambiguous.** The cell is fully inside the structure, but the isodose surface passes through it. The DVH contribution at threshold $d$ is the volume of the sub-region where $D \geq d$. This requires a **single isodose clip** of the full cell (no structure clipping, since the cell is entirely inside).

3. **Boundary + dose-ambiguous.** The cell straddles the structure surface AND the isodose surface passes through the in-structure portion. This requires a **double clip**: first the structure boundary, then the isodose plane.

Category 2 is easily overlooked but matters: for a typical clinical plan with 1 cGy dose bins, each interior cell has a dose range $D_{\max,Q} - D_{\min,Q} \approx |\nabla D| \cdot \sqrt{3}\,\Delta x$ across its diagonal. At 4%/mm gradient and 2.5 mm spacing, that is roughly 10 Gy, so each cell is dose-ambiguous for about 1000 out of 6000 bins. However, for any _single_ bin $d$, only cells along the isodose surface $D = d$ are ambiguous, which scales as $A_{\text{iso}} / \Delta x^2$ where $A_{\text{iso}}$ is the isodose surface area. This is a 2D shell of cells, not the full volume.

Category 3 is geometrically rarer still: the doubly-ambiguous cells lie along the 1D intersection curve of the structure boundary and the isodose surface. Their count scales as $O(L / \Delta x)$ where $L$ is the intersection curve length.

### Solving the dose-ambiguous case: isodose clipping

The declared dose model is piecewise trilinear. A general trilinear function within an interpolation cell has the form:

$$D(\mathbf{r}) = a + bx + cy + dz + exy + fyz + gzx + hxyz$$

Its isosurfaces are bilinear patches, not planes. Exact integration of the thresholded volume under a trilinear field is possible but requires root-finding on the bilinear isosurface.

An alternative is to decompose each cell into 5 or 6 tetrahedra and use piecewise-linear (barycentric) interpolation on each tetrahedron. **This replaces the trilinear dose model with a piecewise-affine surrogate**, on each piece of which the isosurface is truly a plane and the thresholded volume can be computed exactly. The piecewise-affine surrogate agrees with the trilinear model at the grid points (the shared vertices) but differs within each tetrahedron by the dropped cross-terms $exy + fyz + gzx + hxyz$. The surrogate is exact for its own (piecewise-linear) dose model, not for the original trilinear model.

For the purposes of this engine, we adopt a **local affine approximation** to the dose field within each dose-ambiguous cell:

$$D(\mathbf{r}) \approx D_c + \mathbf{g} \cdot (\mathbf{r} - \mathbf{r}_c)$$

where $D_c = D(\mathbf{r}_c)$ is the centre-point dose (evaluated via the trilinear interpolant at the cell centre) and $\mathbf{g}$ is the dose gradient **derived from the eight corner values of the current cell**. For the trilinear interpolant, the gradient at the cell centre can be computed analytically from the corner values. Along each axis, the cell-centre gradient component is the mean of the four finite differences across that axis:

$$g_x = \frac{1}{4\Delta x}\sum_{j \in \{0,1\}} \sum_{k \in \{0,1\}} \left(D_{1jk} - D_{0jk}\right)$$

and analogously for $g_y$ and $g_z$, where $D_{0jk}$ and $D_{1jk}$ are the corner values at the low and high $x$-faces of the cell respectively. This gradient is exact for the trilinear interpolant at the cell centre and uses only the cell's own corner data, maintaining consistency with the declared cellwise trilinear model.

Under this local model, the isodose surface $D = d$ is a plane with normal $\hat{\mathbf{g}} = \mathbf{g} / |\mathbf{g}|$ at signed offset:

$$\phi_D = \frac{d - D_c}{|\mathbf{g}|}$$

from the cell centre. This is analogous to the structure SDF: it defines a half-space, and the volume on the "above threshold" side can be computed using the same PLIC box-plane clipping formula.

**This is an approximation, not an exact evaluation of the trilinear dose model.** The error comes from the cross-terms $exy + fyz + gzx + hxyz$ that the affine model drops. These terms are bounded by $O(\Delta x^2 \cdot |\nabla^2 D|)$, so the approximation improves as the grid becomes finer or the dose field becomes more linear. For most clinical EBRT dose distributions, the cross-terms are expected to be small within a single cell, and the planar isodose approximation is anticipated to perform well; this should be confirmed by benchmarking against tetrahedral decomposition on representative cases. For pathological cases (brachytherapy near a source, very steep SRS penumbra on a coarse grid), the tetrahedral decomposition approach gives exact results under its own piecewise-linear dose model at a cost of approximately 6 tetrahedra per cell (each requiring a separate clip).

The algorithm for each cell at each threshold is:

**Interior dose-ambiguous cell (category 2):**

1. Compute $\phi_D$ and $\hat{\mathbf{g}}$.
2. Clip the full cell by the isodose plane (single PLIC computation).
3. DVH contribution = clipped volume.

**Boundary dose-ambiguous cell (category 3):**

1. Clip the cell by the structure boundary plane to get $P_Q$ (already done during the geometry step).
2. Clip $P_Q$ by the isodose plane to get $P_Q \cap \lbrace D \geq d \rbrace$.
3. DVH contribution = volume of doubly-clipped region.

Under the local affine approximation, both clips are plane-based and the clipped volumes have closed-form expressions. For the **slice-wise 2D approach**, if an explicit polygonal representation of $P_Q$ is available from Sutherland-Hodgman clipping at each $z$-slice, the second clip is another Sutherland-Hodgman pass followed by shoelace area computation, with the result integrated over $z$ by multiplying by $\Delta z$. For a **full 3D approach**, both clips are polyhedron operations (e.g. via r3d [^4]) producing clipped volumes directly.

**Efficient iteration over bins.** For a given cell, the double clip is needed only for dose bins in the range $(D_{\min,Q},\, D_{\max,Q}]$, which is typically a small fraction of all bins. All bins below $D_{\min,Q}$ contribute the full $|P_Q|$; all bins above $D_{\max,Q}$ contribute 0. A practical implementation can pre-sort cells by their dose range, iterate over bins in order, and skip cells whose range does not include the current bin.

### A note on mean dose versus cumulative DVH

The centroid correction from the earlier discussion remains valid and useful for computing **mean structure dose**:

$$\bar{D}_S = \frac{1}{V_S} \sum_Q |P_Q| \cdot D(\mathbf{c}_{P_Q})$$

where $\mathbf{c}_{P_Q}$ is the centroid of the in-structure portion of cell $Q$. Under a local affine dose model, this is exact. But mean dose and cumulative DVH are different quantities. The centroid correction solves the former; the isodose clipping approximates the latter.

## Does the dose grid capture the true dose distribution?

The discussion above assumes the dose grid provided by the TPS is an adequate representation of the dose field. This is a separate and important question from the DVH computation method.

### The dose grid is not a sampling of a pre-existing continuous field

A TPS dose calculation algorithm (AAA, Acuros XB, collapsed cone, Monte Carlo) does not first compute dose on an infinitely fine grid and then downsample to the output resolution. The grid spacing is a parameter of the computation itself. The algorithm solves discretised transport equations (or evaluates discretised convolution kernels) on the chosen grid. Changing the grid spacing changes the computed dose values, not just the sampling of them.

This has been demonstrated empirically. For Eclipse's AAA algorithm, dose differences of up to 7% at $d_{\max}$ between 1 mm and 2.5 mm grid calculations have been reported for small fields [^13]. For Acuros XB, grid size effects are smaller because Acuros uses a fluence pixel size that is always half the calculation grid size. In general, finer grids produce more accurate dose calculations, particularly in regions of steep dose gradients, tissue heterogeneity, and small fields [^12], [^13].

### Supersampling the dose grid does not recover lost information

Trilinear interpolation of a TPS dose grid to a finer resolution produces a smoother representation but does **not** add physical information. The interpolated field is constrained to pass through the original grid values and varies trilinearly between them. If the true dose varies nonlinearly within a cell (as it does in penumbra regions, near heterogeneity interfaces, and near small-field edges), the trilinear interpolation will not capture that variation. The sub-grid dose structure is simply not present in the data.

To obtain dose at finer resolution, the TPS must be asked to **recompute** the dose on a finer grid. This is a fundamentally different operation from interpolation: the algorithm re-evaluates the physics at each new grid point, capturing penumbra structure, lateral scatter, and heterogeneity effects that were averaged away on the coarser grid.

### Implications for DVH accuracy

The DVH computation described in this document is exact (or near-exact) relative to the **declared dose model**, which is the trilinear interpolant of the TPS dose grid. Any dose information not captured by the TPS grid is not recoverable by the DVH engine, regardless of how sophisticated the geometric or threshold handling is.

For conventional EBRT on 2.5 mm grids, the trilinear dose model is adequate for most clinical structures. The physical penumbra width (typically 5--8 mm for conventional 6 MV photon fields [^14]) provides multiple grid points across the steepest gradients.

For SRS/SBRT, the dose grid resolution is itself a significant source of uncertainty, particularly for small targets and small fields. TG-101 [^9] and the 2025 AAPM-RSS update [^10] recommend calculation grids of 2 mm or finer for SBRT, with 1 mm for very small targets. At these resolutions, the trilinear model is better justified, but the dose calculation itself is the limiting factor, not the DVH geometry.

For brachytherapy near sources, the $1/r^2$ dose gradient can change by tens of percent within a single cell at any clinically practical grid spacing. Here, both the TPS dose calculation and the DVH computation face fundamental resolution limits. Adaptive dose integration within boundary cells (as described in the dose-threshold section above) mitigates the DVH side, but the underlying dose grid accuracy remains the binding constraint.

## High curvature and small structures

### When the planar approximation degrades

For a 3 mm diameter brain metastasis ($R = 1.5$ mm) on a 1.0 mm dose grid, the structure spans roughly 3 cells across. Nearly every cell is a boundary cell. The planar sagitta error per cell is approximately:

$$\frac{\Delta x^2}{8R} = \frac{1.0}{12} \approx 0.083 \text{ mm} \approx 8\% \text{ of cell width}$$

Since errors do not cancel as favourably when almost all cells are boundary cells, cumulative DVH error could reach several percent of the total structure volume.

On a 2.5 mm grid, the structure radius (1.5 mm) is smaller than the cell spacing, and the structure diameter (3 mm) spans barely more than one cell. Any algorithm will have large errors at this resolution. This is a sampling problem, not an algorithm limitation. TG-101 [^9] and the 2025 AAPM-RSS update [^10] recommend grid sizes of 2 mm or finer for SBRT, with 1 mm grids for very small targets.

### Quadratic curvature correction (background, not recommended for production)

For theoretical completeness, the next order beyond the planar approximation models the boundary as a **quadric surface** within the cell. In the local tangent frame (with the surface normal along $z$), the surface is:

$$z \approx -\phi + \frac{1}{2}\kappa_1 x^2 + \frac{1}{2}\kappa_2 y^2$$

where $\kappa_1$ and $\kappa_2$ are the principal curvatures ($\kappa = 1/R$).

The volume between this paraboloid and the tangent plane, integrated over the cell face $[-h/2,\, h/2]^2$ (where $h$ is the cell side length), is:

$$\Delta \mathcal{V} = \int_{-h/2}^{h/2}\int_{-h/2}^{h/2} \frac{1}{2}(\kappa_1 x^2 + \kappa_2 y^2)\,dx\,dy = \frac{(\kappa_1 + \kappa_2)\,h^4}{24}$$

using $\int_{-h/2}^{h/2} x^2\,dx = h^3/12$. Dividing by the cell volume $h^3$ gives the fractional volume correction for isotropic cells:

$$\Delta f = \frac{(\kappa_1 + \kappa_2)\,h}{24} = \frac{H\,h}{12}$$

where $H = (\kappa_1 + \kappa_2)/2$ is the mean curvature. For convex surfaces ($\kappa > 0$ with outward-positive convention), the planar model overestimates the interior volume, so the correction is subtracted:

$$f_{\text{corrected}} = f_{\text{planar}} - \frac{H\,h}{12}$$

**However, this correction is not recommended for production use** for three reasons:

1. The error bound for the corrected method has not been derived in this document. The leading-order correction scales as $Hh$, but the residual error (from higher-order curvature terms, non-isotropic cells, and oblique normals) is not characterised.
2. The mean curvature $H$ must be estimated from the SDF via finite differences. The standard level-set formula [^3] (eq. 1.12) requires second derivatives of $\phi$, including the cross-plane derivatives $\phi_{zz}$, $\phi_{xz}$, $\phi_{yz}$. Since $\phi$ is linearly interpolated in $z$, $\phi_{zz} = 0$ between contour slices and the mixed derivatives $\phi_{xz}$, $\phi_{yz}$ are only first-order accurate. The resulting curvature estimate captures in-plane curvature but is unreliable for out-of-plane curvature (e.g. the superior dome of the bladder, or a small spherical target where contour radius changes rapidly between slices).
3. Exact polygon-cell clipping (below) is cheap for the small structures where curvature matters most, and its error is machine precision.

For these reasons, the recommended production dispatch is **binary**: planar PLIC for low-curvature cells, exact clipping for everything else. The SDF curvature estimate is useful as a _dispatch criterion_ (to detect which cells need exact clipping) but should not be used for the volume computation itself. If the curvature correction is later benchmarked and validated against exact clipping for representative clinical geometries, it could be restored as a middle tier.

### Exact analytical clipping

When the curvature correction is insufficient, or when machine-precision reference values are needed for validation, compute the **exact polygon-cell intersection**.

#### The 2D Sutherland-Hodgman algorithm

For each contour slice, the problem reduces to 2D: clip a contour polygon against the axis-aligned bounding box of each boundary cell. The Sutherland-Hodgman algorithm [^7] clips a polygon against a single half-plane by walking the vertex list and emitting output vertices according to four cases:

For each directed edge from vertex $\mathbf{p}_i$ to $\mathbf{p}_{i+1}$, and a clip boundary defined by $\mathbf{n} \cdot \mathbf{r} \leq c$:

- Both inside ($\mathbf{n} \cdot \mathbf{p}_i \leq c$ and $\mathbf{n} \cdot \mathbf{p}_{i+1} \leq c$): emit $\mathbf{p}_{i+1}$.
- Inside to outside: emit the intersection point $\mathbf{p}_i + t(\mathbf{p}_{i+1} - \mathbf{p}_i)$ where $t = (c - \mathbf{n} \cdot \mathbf{p}_i) / (\mathbf{n} \cdot (\mathbf{p}_{i+1} - \mathbf{p}_i))$.
- Both outside: emit nothing.
- Outside to inside: emit the intersection point, then $\mathbf{p}_{i+1}$.

A cell's bounding box has four edges (left, right, bottom, top), so four sequential clips produce the exact polygon-cell intersection. The result is a (possibly empty) convex or non-convex polygon.

#### Computing the clipped area via the shoelace formula

Given the clipped polygon with $n$ vertices $\lbrace(x_1, y_1), \ldots, (x_n, y_n)\rbrace$ in order, the signed area is:

$$A = \frac{1}{2} \left| \sum_{i=1}^{n} (x_i\, y_{i+1} - x_{i+1}\, y_i) \right|$$

where indices wrap ($x_{n+1} = x_1$, $y_{n+1} = y_1$). This is exact to floating-point precision.

The centroid of the clipped polygon (needed for the mean-dose correction) is:

$$\bar{x} = \frac{1}{6A} \sum_{i=1}^{n} (x_i + x_{i+1})(x_i\, y_{i+1} - x_{i+1}\, y_i)$$

with an analogous expression for $\bar{y}$.

#### Assembling the 3D volume from slice-wise 2D clipping

The 2D Sutherland-Hodgman algorithm clips contour polygons at individual $z$-slices. To obtain a 3D volume, the slice-wise clipped areas must be integrated over $z$.

For a structure defined by contours on slices $z_k$ and $z_{k+1}$, and a dose grid $z$-plane at height $z$ between them, we need the clipped area at height $z$. The simplest approach clips the contour polygon on each bracketing slice and linearly interpolates the resulting areas:

$$A(z) \approx (1-\alpha)\,A(z_k) + \alpha\,A(z_{k+1})$$

**This is an approximation.** Even when contour geometry varies linearly with $z$ (e.g. a linearly tapering radius), the enclosed area varies quadratically ($A = \pi r^2$), so linear area interpolation introduces error. The volume contribution is then:

$$|P_Q| \approx A(z) \cdot \Delta z$$

A more accurate slice-wise approach is to compute the 2D SDF at the dose grid $z$-height by interpolating the bracketing 2D SDFs (as defined in the chosen reconstruction model, Step 2), extract or reconstruct the zero-level contour at that height, clip it against the cell, and compute the clipped area directly. This gives the correct area for the linearly interpolated SDF model.

#### The r3d library for full 3D clipping

For cases where the slice-wise 2D approach is insufficiently accurate or where a true 3D polyhedral representation of the structure is available, the **r3d** library [^4] provides full 3D polyhedron-cell intersection. Its core operation clips a convex polyhedron against a sequence of half-planes using a vertex-connected graph representation. From the clipped polyhedron, it computes coordinate moments of arbitrary order via the recursive reduction of Koehl [^5], which applies the divergence theorem to reduce volume integrals to surface integrals to line integrals to vertex evaluations.

Note that r3d operates on explicit polyhedral geometry. To use it with the SDF reconstruction model, the implicit zero level set must first be converted to an explicit surface mesh (e.g. via marching cubes). This is an additional extraction step that introduces its own approximation (the marching-cubes triangulation) unless the mesh resolution is sufficiently fine.

For zeroth-order moments (volume) and first-order moments (centroid), the computation is $O(F)$ per clip plane, where $F$ is the number of faces of the polyhedron. A cell is a 6-faced polyhedron; clipping against a contour-derived surface adds faces proportional to the number of contour edges that cross the cell (typically 2--4 for clinical contours at clinical grid spacing). The total cost per cell is modest.

Powell and Abel [^4] report machine-precision accuracy ($\sim 10^{-14}$ relative error in volume). For clinical DVH with at most a few thousand boundary cells, r3d is far faster than needed. The library is written in C with no external dependencies and is straightforward to wrap via pybind11 or ctypes.

For non-convex polyhedra (which can arise from complex contour topologies), the Interface Reconstruction Library [^6] provides a half-edge-based alternative that handles arbitrary polyhedra.

#### Boundary cell count for small structures

For a 3 mm diameter sphere ($R = 1.5$ mm) on a 1 mm isotropic grid, how many boundary cells are there? This depends on the sphere's alignment with the grid. A cell is classified as "boundary" when the structure surface passes through it, which occurs when $|\phi(\mathbf{c}_Q)| < \ell$ (the half-diagonal, $\approx 0.87$ mm for a 1 mm isotropic cell).

Enumeration over both best-case and worst-case alignments gives approximately **56 boundary cells** total across 4--5 slices, with only 0--1 fully interior cells. The per-slice breakdown for a centred sphere is approximately 5, 13, 20, 13, 5 boundary cells from inferior to superior. For a corner-aligned sphere: 12, 16, 16, 12. In either case, this is roughly 56 clipping operations for the entire structure, not hundreds. Exact clipping of 56 cells is trivially fast.

## Commercial system taxonomy

Before describing the tiered dispatch adopted by this engine, it is useful to situate the approach within the landscape of commercial DVH implementations. Published multi-system comparisons [^11], [^20], [^21] reveal at least four major families of volume construction method and significant variation in binning and metric extraction policies.

### Volume construction families

**Right-prism and half-slice extension methods.** The structure is extruded vertically from each contour slice by half the slice spacing in each direction. Voxels are tested against these extruded slabs. Variants include extending by exactly half a slice (Mobius3D, MIM, RayStation) or capping the extension at a maximum distance such as 1.5 mm (ProKnow). These methods are simple and deterministic but produce flat superior/inferior caps with no anatomical rounding.

**Shape-based interpolation with rounded or shape-based endcaps.** The structure boundary between slices is interpolated using morphological or distance-field methods, and the superior/inferior ends are closed with rounded caps derived from the interpolation model. Eclipse uses a shape-based interpolation approach with rounded endcaps that approximate the anatomical closure of the structure.

**Supersampled point or voxel methods.** Each voxel is subdivided into sub-voxels (or sample points are placed within each voxel), and the occupancy fraction is estimated from the count of sub-samples falling inside the structure. The supersampling factor varies by vendor and is often user-configurable. This family treats volume construction and dose sampling together.

**Adaptive or relative-volume methods.** Some systems (e.g. Elements) allow contours to exist in 3D space without strict axial-slice constraints, or use native 3D mesh representations. These systems may avoid classical end-capping artefacts but introduce their own interpolation and discretisation choices.

### Binning and metric extraction

Dose-bin resolution, histogram normalisation, and the method used to extract point metrics ($D_{x\%}$, $V_{x\,\text{Gy}}$) from the binned histogram also vary across systems. Some use linear interpolation between bin edges; others report the nearest bin. Bin widths range from 0.01 Gy to 1 cGy in common configurations. These differences contribute measurably to cross-system DVH metric disagreement.

### Implications for this engine

The approach described in this document (SDF-based implicit geometry with analytical PLIC clipping and configurable end-capping) does not fall neatly into any of the commercial families above. It is closest to the distance-field family but uses analytical volume fractions rather than supersampled occupancy. The commercial taxonomy motivates making every modelling choice (interpolation model, end-cap policy, binning resolution, metric extraction rule) explicit and configurable, so that the engine's behaviour can be compared meaningfully against any of the commercial families.

## Tiered dispatch

Route each boundary cell to the cheapest method that meets accuracy requirements. The geometry tier dispatches on $|\kappa| \cdot \Delta x$; the dose tier dispatches on the cell corner doses at each threshold. The threshold values 0.1 and 0.5 below are provisional design heuristics, not validated cut-offs; they should be benchmarked against exact clipping for representative clinical geometries before production use.

```text
For each boundary cell Q:

    Compute phi, grad_phi.
    Estimate mean curvature kappa from SDF Hessian (for dispatch only).

    # --- Geometry tier: compute in-structure volume |P_Q| ---
    if |kappa| * dx < threshold:  planar PLIC volume fraction
    else:                         exact polygon-cell clipping

    # --- Dose tier: for each threshold d ---
    Evaluate D at the 8 cell corners -> D_min, D_max.

    if D_min >= d:              DVH contribution = |P_Q|
    elif D_max < d:             DVH contribution = 0
    else:                       clip P_Q by local affine isodose plane
```

The curvature threshold should be chosen so that the planar PLIC error is acceptable for the application. A provisional starting point is $|\kappa| \cdot \Delta x < 0.2$ (corresponding to $\Delta x / R < 0.2$, or roughly 1--2% per-cell geometric error), but this should be benchmarked against exact clipping for representative clinical structures before production use.

## Worked examples

### Geometry: 1D, uniform dose

A 1D cell from $x = 0$ to $x = \Delta x = 2.5$ mm. Structure boundary at $x_b = 1.8$ mm. Dose is uniform at 60 Gy.

**Binary method.** Cell centre at $x_c = 1.25$ mm is inside ($1.25 < 1.8$), so $v = 2.5$ mm. True interior: 1.8 mm. Error: +0.7 mm (+39%).

**4x supersampled binary.** Sub-centres at 0.3125, 0.9375, 1.5625, 2.1875 mm. The first three are inside ($< 1.8$), so $v = 3/4 \times 2.5 = 1.875$ mm. Error: +0.075 mm (+4.2%).

**SDF method.** The signed distance at the cell centre is $\phi = -(1.8 - 1.25) = -0.55$ mm (negative because the centre is inside). Using $f = 1/2 - \phi / \Delta x$:

$$f = \frac{1}{2} - \frac{-0.55}{2.5} = 0.72$$

$$v = 0.72 \times 2.5 = 1.8 \text{ mm}$$

Error: 0. Exact in 1D because the boundary is a point (infinite radius of curvature, so the planar approximation is perfect).

### Dose-threshold: 1D, non-uniform dose

Same geometry, but dose varies linearly: $D(x) = 60 + 4(x - 1.25)$ Gy. In-structure region $[0, 1.8]$ mm.

**Mean dose** (centroid correction). The interior centroid is at $x = 0.9$ mm. Dose there: $D(0.9) = 58.6$ Gy. Product: $58.6 \times 1.8 = 105.48$ Gy-mm. True integral: $\int_0^{1.8}[55 + 4x]\,dx = 105.48$ Gy-mm. Exact.

**DVH at $d = 60$ Gy** (the dose-threshold problem). Inside the structure, the dose exceeds 60 Gy only where $x \geq 1.25$. The true in-structure length above threshold is $1.8 - 1.25 = 0.55$ mm.

If we threshold the centroid dose 58.6 Gy, the result is 0 mm (wrong). If we threshold the centre-point dose 60.0 Gy, the result depends on the tie-breaking convention (wrong either way).

**Double-clip method.** The structure boundary is at $x = 1.8$ (from the SDF). The isodose surface $D = 60$ Gy is at $x = 1.25$ (from the dose gradient). The in-structure region above threshold is the intersection: $[0, 1.8] \cap [1.25, \infty) = [1.25, 1.8]$. Length = 0.55 mm. **Exact under the linear dose model.**

## Accuracy summary

| Method | Geometric error | DVH threshold | Supersampling? |
| --- | --- | --- | --- |
| Binary centre-point | up to $\pm\Delta V$ | up to $\pm\Delta V$ | No (inaccurate) |
| $k\times$ supersampled | $O(1/k)$ | $O(1/k)$ | Yes, $k^3\times$ cost |
| SDF + planar PLIC | $O(\Delta x / R)$ | affine approx. | **No** |
| Exact polygon clipping | machine precision | affine approx. | **No** |

The geometric error column refers to the per-boundary-cell volume fraction error. The DVH threshold column refers to how the dose-threshold discontinuity is handled: the corner min/max test is exact for the trilinear dose model on interpolation cells, but the isodose plane clipping uses a local affine approximation (see earlier discussion). For most clinical EBRT cases the affine approximation is expected to perform well; this should be confirmed by benchmarking against tetrahedral decomposition on representative cases. For the trilinear model specifically, tetrahedral decomposition provides exact results under a piecewise-linear surrogate at higher cost.

## The complete algorithm

```text
Input:
    RTSTRUCT contours
    RTDOSE array
    Dose model (e.g., trilinear interpolation)
    Dose bin thresholds d_1, ..., d_B

0. Assess contour vertex fidelity
    For each contour slice:
        Compute chord lengths, estimate radii, flag sparse contours.
        Warn if maximum chord length exceeds sagitta tolerance for
        the expected structure radius.
        Report input-data quality metrics.

1. Build the structure model
    a. Parse contours in patient coordinates.
    b. Normalise keyhole and CLOSEDPLANAR_XOR semantics.
       (If any contour in an ROI uses CLOSEDPLANAR_XOR,
       verify all contours in that ROI are of that type.)
    c. For each contour slice k, compute exact 2D signed distances
       from dose grid (x, y) points to the contour polygon.
    d. For dose grid z-planes between contour slices, linearly
       interpolate the 2D SDFs.
    e. Apply end-cap model beyond superior/inferior contour slices.
    f. (Recommended) Reinitialise to approximate Euclidean SDF via
       fast marching.

2. Classify interpolation cells (structure geometry)
    After reinitialisation (distance-based):
        half_diag = 0.5 * sqrt(dx^2 + dy^2 + dz^2)
        interior  = (phi(centre) < -half_diag)
        exterior  = (phi(centre) > +half_diag)
        boundary  = everything else

    Without reinitialisation (sign-only):
        interior  = (phi < 0 at all 8 corners)
        exterior  = (phi > 0 at all 8 corners)
        boundary  = everything else

3. Compute in-structure volumes for boundary cells
    For each boundary cell Q:
        Estimate surface normal from grad(phi).
        If needed: estimate curvature from Hessian(phi).

        Geometry dispatch (curvature used for dispatch only):
            |kappa| * dx < threshold  ->  planar PLIC fraction
            else                      ->  exact polygon-cell clipping

        Store |P_Q| (and optionally the clipped polygon for later
        isodose clipping).

4. Pre-compute dose corner values
    For each non-exterior cell Q:
        Read dose at 8 cell corners (the grid points bounding Q).
        Store D_min_Q and D_max_Q.

5. Evaluate DVH
    Initialise V(d_b) = 0 for each bin.

    For each interior cell Q:
        For each bin d_b:
            if D_min_Q >= d_b:
                Add Delta_V.
            elif D_max_Q < d_b:
                Add 0.
            else:
                (Interior dose-ambiguous: single isodose clip)
                Compute cell-local dose gradient g from 8 corners.
                Clip full cell by isodose plane D = d_b.
                Add clipped volume.

    For each boundary cell Q:
        For each bin d_b:
            if D_min_Q >= d_b:
                Add |P_Q|.
            elif D_max_Q < d_b:
                Add 0.
            else:
                (Boundary dose-ambiguous: double clip)
                Compute cell-local dose gradient g from 8 corners.
                Clip P_Q by isodose plane D = d_b.
                Add doubly-clipped volume.

6. Normalise
    V_total = sum of all |P_Q| + sum of interior Delta_V
    DVH(d_b) = V(d_b) / V_total
```

**No global geometric supersampling is required.** The structure geometry is resolved analytically (or near-analytically) from the contour vertices. The dose threshold is resolved via the corner classification and, where needed, local affine isodose clipping. Both discontinuities in the DVH integral are handled via targeted local methods rather than brute-force subdivision.

## Summary

Both the structure boundary and the isodose surfaces are discontinuities in the DVH integrand. The SDF approach resolves the geometric discontinuity analytically, replacing binary cell classification with sub-cell volume fractions that are exact under the planar model and highly accurate for most clinical geometries. The corner-dose classification resolves the dose-threshold discontinuity for most cells immediately, and local affine isodose clipping handles the remainder as a first-order approximation to the trilinear dose model.

Together, these methods closely approximate the DVH integral at the native grid resolution, with targeted local refinement only where discontinuity surfaces intersect a cell. The approximations involved (planar structure boundary, affine dose model, linearly interpolated inter-slice SDF) are made explicit, and each can be replaced with a more accurate method (curvature correction, tetrahedral decomposition, SDF reinitialisation) where needed.

Supersampling, subdividing space into finer binary grids, is a brute-force approach to both discontinuities simultaneously. The SDF approach separates them, handles each one with targeted analytical methods, and is expected to achieve better accuracy at lower cost for typical clinical cases. This expectation should be confirmed by systematic benchmarking (see the validation roadmap below).

Published cross-system comparisons [^11], [^20], [^21] show that commercial DVH calculators can differ from one another by approximately 0.9--3.2% in DVH metrics, with the major sources of variation being supersampling strategy, end-capping policy, and dose bin resolution. The approach described here makes each of these choices explicit and handles them with targeted analytical methods, rather than leaving them as hidden implementation details.

## Validation roadmap

The algorithm described in this document makes specific claims about accuracy that require systematic benchmarking before they can be presented as demonstrated results. The following validation matrix outlines the minimum benchmark suite.

### Analytical phantom tests

**Nelms-style geometries [^20].** Spheres, cylinders, and cones at known positions relative to analytical dose fields (uniform, linear gradient, quadratic). These provide closed-form DVH solutions for algorithm verification with clean error attribution.

**Pepin-style precision tests [^11].** Cone and cylinder geometries on grids of varying resolution, testing convergence of volume, $D_{\text{mean}}$, $D_{95\%}$, and $V_{x\,\text{Gy}}$ as a function of grid spacing and structure size.

**Stanley small-sphere SRS cases [^22].** Spheres of 3--10 mm diameter on 1 mm grids in steep gradient fields, specifically targeting the regime where both contour vertex fidelity and boundary-cell clipping accuracy are stressed.

**Grammatikou 1 mm SRS regime [^23].** Intracranial SRS targets at 1 mm slice spacing and 1 mm dose grid, benchmarking GI, CI, and volume accuracy against TPS reference values.

### Contour vertex fidelity sweep

**Vertex decimation tests.** For circular and spherical contours, systematically reduce vertex count from 64 to 4 and measure the resulting DVH error (structure volume, $D_{95\%}$, $V_{100\%}$) as a function of vertex count and structure radius. This isolates the input-data fidelity error from the algorithmic error.

### Cross-method convergence

**Planar PLIC vs exact clipping.** For each analytical phantom, compute the DVH using both the planar PLIC path and the exact polygon-cell clipping path. The difference quantifies the curvature-induced error of the planar model and validates the curvature-based dispatch threshold.

**Affine vs tetrahedral dose model.** For dose-ambiguous cells, compare the affine isodose approximation against the tetrahedral decomposition. This quantifies the dose-side model error and identifies cases where the affine model is insufficient.

### Clinical dataset stress tests

Analytical phantoms do not reproduce the full complexity of clinical anatomy. A small set of clinical RTSTRUCT/RTDOSE pairs should be selected to cover concavities, thin shells, multiply connected structures, and structures in steep-gradient regions. The engine's output should be compared against commercial TPS DVH values and, where possible, against a converged high-resolution reference (e.g. exact clipping on a 0.5 mm interpolated grid).

## Further directions from computer graphics

The algorithm described above draws primarily on the Volume of Fluid literature for its clipping machinery. Several additional techniques from computer graphics and computational geometry could improve specific aspects of the DVH pipeline.

**Bounding volume hierarchies (BVHs) for the 2D SDF computation.** _Improves: speed of SDF computation for complex contours._ The vectorised point-to-segment loop in Step 1 is $O(M \cdot N)$ where $M$ is the number of grid points and $N$ the number of contour edges. For organs with complex contours ($N > 500$, e.g. lung with mediastinal invaginations), this becomes the bottleneck. Building a 2D BVH or R-tree over the edges and querying nearest-edge per grid point reduces this to $O(M \log N)$. Libraries like Shapely (GEOS backend) provide this via `STRtree`. This does not affect DVH accuracy, only computation time.

**Robust 2D winding numbers** [^16]. _Improves: robustness of the inside/outside sign determination._ The crossing-number test used for SDF sign determination can produce spurious sign flips when contour edges pass near grid points or when contours have near-degenerate vertices. A robust planar winding number formulation sums the signed angle subtended by each contour edge as seen from the query point; the integer part of the result gives the winding number, and the fractional part degrades gracefully for imperfect geometry. For the 2D slice-wise problem considered here, this is a planar winding number computation, not the 3D solid-angle formulation described by Jacobson et al. [^16] for triangle soups. The fast winding number variant [^17] (which uses hierarchical multipole approximation to achieve $O(\log N)$ complexity) is relevant only if the engine later reconstructs an explicit 3D surface mesh; for the 2D per-slice problem, a direct $O(N)$ winding number computation is sufficient and simpler.

**Sparse volumetric storage.** _Improves: memory efficiency for many structures or large grids._ For a patient with 30 structures on a 256 x 256 x 100 dose grid, storing a full SDF array per structure requires roughly 600 MB of float32 data. OpenVDB [^18] stores only a narrow band around each structure boundary, compressing uniform interior/exterior regions to tiles. For typical clinical structures, this is expected to reduce storage substantially (estimated 10--100x; these figures should be benchmarked for clinical datasets). NanoVDB provides a GPU-friendly read-only variant. Python bindings are available via `pyopenvdb`. This does not affect accuracy but enables scaling to large structure sets.

**GPU acceleration.** _Improves: total DVH computation time._ The per-slice SDF computation and the per-cell PLIC clipping are both embarrassingly parallel. NVIDIA Warp (`pip install warp-lang`) JIT-compiles Python spatial computing kernels to CUDA with built-in mesh BVH queries. Taichi Lang (`pip install taichi`) compiles to CUDA, Vulkan, or Metal with native sparse data structure support. GPU acceleration would primarily benefit batch processing (e.g. recomputing DVHs across a plan comparison study) rather than single-plan clinical use, where CPU performance is likely adequate.

**Morphological contour interpolation.** _Improves: inter-slice structure model for complex topologies._ The ITK `MorphologicalContourInterpolator` (Zukic et al., _Insight J._, 2016) uses iterative dilation/erosion to transform one contour toward another, handling branching and topology changes more naturally than linear SDF interpolation. It produces a binary interpolation that can be converted to an SDF via fast marching. This could improve DVH accuracy for structures with complex between-slice behaviour (e.g. the horseshoe-shaped parotid, or structures that branch between slices) at the cost of a more expensive inter-slice reconstruction step.

**Fast marching for SDF reinitialisation.** _Improves: reliability of the half-diagonal cell classification and curvature dispatch._ As discussed earlier, the linearly interpolated SDF is not a true Euclidean distance field. Reinitialising it by solving the Eikonal equation $|\nabla\phi| = 1$ with the zero level set held fixed produces an approximate Euclidean SDF. scikit-fmm (`pip install scikit-fmm`) implements this in $O(N \log N)$ on 3D NumPy arrays. After reinitialisation, the half-diagonal classification test becomes well-founded (subject to the $O(\Delta x)$ discretisation error of the fast marching solver), and curvature estimates from the SDF Hessian become more reliable. This directly improves correctness of cell classification and the curvature-based dispatch criterion.

## Bibliography

[^1]: Scardovelli R, Zaleski S. Analytical relations connecting linear interfaces and volume fractions in rectangular grids. _J Comput Phys_. 2000;164(1):228-237. doi:10.1006/jcph.2000.6567.

[^2]: Lehmann M, Gekle S. Analytic solution to the piecewise linear interface construction problem and its application in curvature calculation for volume-of-fluid simulation codes. _Computation_. 2022;10(2):21. doi:10.3390/computation10020021.

[^3]: Osher S, Fedkiw R. _Level Set Methods and Dynamic Implicit Surfaces_. New York: Springer; 2003.

[^4]: Powell D, Abel T. An exact general remeshing scheme applied to physically conservative voxelization. _J Comput Phys_. 2015;297:340-356. doi:10.1016/j.jcp.2015.05.022.

[^5]: Koehl P. Fast recursive computation of 3D geometric moments from surface meshes. _IEEE Trans Pattern Anal Mach Intell_. 2012;34(11):2158-2163. doi:10.1109/TPAMI.2012.23.

[^6]: Chiodi R, Desjardins O. General, robust, and efficient polyhedron intersection in the Interface Reconstruction Library. _J Comput Phys_. 2022;449:110787. doi:10.1016/j.jcp.2021.110787.

[^7]: Sutherland IE, Hodgman GW. Reentrant polygon clipping. _Commun ACM_. 1974;17(1):32-42. doi:10.1145/360767.360802.

[^8]: Sunderland K, Woo B, Pinter C, Fichtinger G. Reconstruction of surfaces from planar contours through contour interpolation. _Proc SPIE_. 2015;9415:94151R. doi:10.1117/12.2081367.

[^9]: Benedict SH, Yenice KM, Followill D, et al. Stereotactic body radiation therapy: the report of AAPM Task Group 101. _Med Phys_. 2010;37(8):4078-4101. doi:10.1118/1.3438081.

[^10]: Cirino E, Anastasi G, Bresciani S, et al. AAPM-RSS Medical Physics Practice Guideline 9.b on stereotactic body radiation therapy. _J Appl Clin Med Phys_. 2025;26(4):e14624. doi:10.1002/acm2.14624.

[^11]: Pepin MD, Langner U, Bolen SD, et al. Assessment of dose-volume histogram precision for five clinical systems. _Med Phys_. 2022;49(10):6303-6318. doi:10.1002/mp.15916.

[^12]: Huang B, Wu L, Lin P, Chen C. Dose calculation of Acuros XB and Anisotropic Analytical Algorithm in lung stereotactic body radiotherapy treatment with flattening filter free beams and the potential role of calculation grid size. _Radiat Oncol_. 2015;10:53. doi:10.1186/s13014-015-0357-0.

[^13]: Ong CL, Verbakel WFAR, Cuijpers JP, Slotman BJ, Lagerwaard FJ, Senan S. Impact of the calculation resolution of AAA for small fields and RapidArc treatment plans. _Med Phys_. 2011;38(8):4471-4479. doi:10.1118/1.3605468.

[^14]: Khan FM, Gibbons JP. _Khan's the Physics of Radiation Therapy_. 6th ed. Philadelphia: Wolters Kluwer; 2020.

[^15]: DICOM Standards Committee. DICOM PS3.3: Information Object Definitions. Current edition. Sections C.8.8.3 (RT Dose Module) and C.8.8.6.3 (ROI Contour Module). <https://dicom.nema.org/medical/dicom/current/output/chtml/part03/sect_C.8.8.3.html>

[^16]: Jacobson A, Kavan L, Sorkine-Hornung O. Robust inside-outside segmentation using generalised winding numbers. _ACM Trans Graph_. 2013;32(4):33. doi:10.1145/2461912.2461916.

[^17]: Barill G, Dickson NG, Schmidt R, Levin DIW, Jacobson A. Fast winding numbers for soups and clouds. _ACM Trans Graph_. 2018;37(4):43. doi:10.1145/3197517.3201337.

[^18]: Museth K. VDB: High-resolution sparse volumes with dynamic topology. _ACM Trans Graph_. 2013;32(3):27. doi:10.1145/2487228.2487235.

[^19]: dicompyler-core contributors. dicompyler-core: A library for DICOM RT DVH calculation. <https://github.com/dicompyler/dicompyler-core>.

[^20]: Nelms BE, Tome WA, Robinson G, Wheeler J. Variations in the contouring of organs at risk: test case from a patient with oropharyngeal cancer. _Int J Radiat Oncol Biol Phys_. 2012;82(1):368-378. Note: the Nelms DVH benchmark methodology is described in Nelms BE, Robinson G, Markham J, et al. Variation in external beam treatment plan quality: An inter-institutional study of planners and planning systems. _Pract Radiat Oncol_. 2012;2(4):296-305; the analytical DVH validation dataset is published in Nelms BE, et al. Methods, software and datasets to verify DVH calculations against analytical values: Twenty years late(r). _Med Phys_. 2015;42(6):3380. doi:10.1118/1.4924390.

[^21]: Penoncello GP, Sechrest SA, Chou W, et al. Multicenter multivendor evaluation of dose volume histogram creation consistencies for 8 commercial radiation therapy dosimetric systems. _Pract Radiat Oncol_. 2024;14(4):e316-e324. doi:10.1016/j.prro.2024.03.002.

[^22]: Stanley DN, Harms J, Pogue JA, et al. Accuracy of dose-volume metric calculation for small-volume radiosurgery targets. _Med Phys_. 2021;48(10):6511-6520. doi:10.1002/mp.15216.

[^23]: Grammatikou P, Leventouri I, Georgakilas AG, et al. Validation of dose-volume calculation accuracy for intracranial stereotactic radiosurgery with volumetric-modulated arc therapy using analytical and clinical treatment plans. _Appl Radiat Isot_. 2025;218:111733. doi:10.1016/j.apradiso.2025.111733.
