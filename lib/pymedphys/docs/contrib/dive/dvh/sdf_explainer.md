# Signed Distance Field (SDF) Explainer

## The fundamental problem

You have a 3D dose grid $D(i,j,k)$ and a structure $S$ defined by contour polygons on CT slices. You need to compute:

$$
\text{DVH}(d) = \frac{1}{V_S} \sum_{\text{voxels}} v_{ijk} \cdot \mathbf{1}[D(i,j,k) \geq d]
$$

where $V_S = \sum v_{ijk}$ is the total structure volume and $v_{ijk}$ is **the volume of voxel $(i,j,k)$ that lies inside $S$**.

The entire DVH accuracy problem reduces to computing $v_{ijk}$ correctly for every voxel. For voxels fully inside or fully outside the structure, this is trivial ($v_{ijk} = \Delta x \Delta y \Delta z$ or $0$). The hard part is **boundary voxels** — those that the structure surface passes through.

But there is actually a second, subtler problem: even if you know $v_{ijk}$ perfectly, the DVH computation implicitly assumes the dose is uniform across the interior portion of each boundary voxel. When dose gradients are steep, this assumption breaks down. A complete treatment must address both the geometric and dosimetric contributions to DVH error.

---

## What the naïve method does (and why it's wrong)

The standard approach (dicompyler, plastimatch, etc.) does this per CT slice:

1. Rasterise the contour polygon to a binary mask on the dose grid
2. For each dose-grid point $(x_i, y_j)$, test: is the centre point inside the polygon?
3. If yes, assign $v_{ijk} = \Delta x \Delta y \Delta z$. If no, assign $v_{ijk} = 0$.

This is a **centre-point sampling** scheme. It makes a catastrophic binary decision at every boundary voxel: a voxel that is 99% inside the structure gets $v = \Delta V$, but a voxel that is 49% inside gets $v = 0$. The error per boundary voxel can be up to $\pm \Delta V$.

How many boundary voxels are there? For a roughly spherical structure of radius $R$ on a grid with spacing $\Delta x$:

$$
N_{\text{boundary}} \sim \frac{4\pi R^2}{\Delta x^2}
$$

For a 5 cm radius sphere on a 2.5 mm grid, that's ~50,000 boundary voxels, each with a potential error of up to $\Delta V$. The errors partially cancel (some voxels are over-counted, others under-counted), but the residual is significant — especially for small structures where boundary voxels are a large fraction of total voxels.

---

## What supersampling does (and its cost)

Supersampling subdivides each voxel into $k \times k \times k$ sub-voxels and tests each sub-voxel centre:

$$
v_{ijk} \approx \frac{\Delta V}{k^3} \sum_{a=1}^{k} \sum_{b=1}^{k} \sum_{c=1}^{k} \mathbf{1}[(x_a, y_b, z_c) \in S]
$$

At $k=4$, you get 64 samples per boundary voxel. The fractional volume estimate has a resolution of $1/64 \approx 1.6\%$. Better, but:

- Memory: $k^3$ increase (64× at $k=4$)
- Compute: $k^3$ point-in-polygon tests per boundary voxel
- Accuracy: still limited to $1/k^3$ resolution
- **Crucially: you're still rasterising to binary decisions**, just on a finer grid. You've still thrown away the contour geometry.

---

## The key insight: contour polygons encode exact boundary positions

Here's what everyone seems to miss. Your DICOM RT Structure Set contains polygon vertices with coordinates specified to sub-millimetre precision. A contour polygon edge between vertices $(x_1, y_1)$ and $(x_2, y_2)$ defines the **exact** boundary of the structure at that slice height. The boundary position is known analytically — it's a piecewise-linear curve.

When you rasterise to a binary mask, you **destroy** this information. You replace a boundary known to ~0.1 mm precision with one known to ${\sim}\Delta x/2 \approx 1.25$ mm precision. Supersampling recovers some of it ($\Delta x / 2k$), but you're still approximating a known line with a staircase.

The SDF approach preserves this information exactly.

---

## Signed Distance Fields from first principles

### Definition

For a closed surface $\partial S$ (in 2D, a closed polygon), the signed distance function is:

$$
\phi(\mathbf{p}) = \begin{cases} -d(\mathbf{p}, \partial S) & \text{if } \mathbf{p} \in S \\ +d(\mathbf{p}, \partial S) & \text{if } \mathbf{p} \notin S \end{cases}
$$

where $d(\mathbf{p}, \partial S) = \min_{\mathbf{q} \in \partial S} \|\mathbf{p} - \mathbf{q}\|$ is the minimum Euclidean distance from $\mathbf{p}$ to the boundary.

The zero level set $\{\mathbf{p} : \phi(\mathbf{p}) = 0\}$ is precisely the boundary $\partial S$.

### Computing it exactly from polygon edges (2D, per slice)

Consider a single contour polygon with $N$ vertices $\{\mathbf{v}_0, \mathbf{v}_1, \ldots, \mathbf{v}_{N-1}\}$ and $N$ edges. For a query point $\mathbf{p} = (p_x, p_y)$, we need:

**Step 1: Unsigned distance to the polygon boundary.**

For each edge $e_m$ from $\mathbf{v}_m$ to $\mathbf{v}_{m+1}$, compute the distance from $\mathbf{p}$ to the line segment:

$$
\mathbf{e} = \mathbf{v}_{m+1} - \mathbf{v}_m
$$

$$
t = \text{clamp}\left(\frac{(\mathbf{p} - \mathbf{v}_m) \cdot \mathbf{e}}{\mathbf{e} \cdot \mathbf{e}},\ 0,\ 1\right)
$$

$$
\mathbf{q}_m = \mathbf{v}_m + t\,\mathbf{e}
$$

$$
d_m = \|\mathbf{p} - \mathbf{q}_m\|
$$

The unsigned distance is:

$$
d(\mathbf{p}, \partial S) = \min_{m=0}^{N-1} d_m
$$

**Step 2: Determine the sign (inside/outside).**

Use the **crossing number** (ray casting) test. Cast a ray from $\mathbf{p}$ in the $+x$ direction and count edge crossings. Odd count → inside (negative sign). Even count → outside (positive sign).

Or equivalently, compute the **winding number**: sum the signed angles subtended by each edge as seen from $\mathbf{p}$. Non-zero winding number → inside.

**Step 3: Apply the sign.**

$$
\phi(\mathbf{p}) = \text{sign}(\mathbf{p}) \cdot d(\mathbf{p}, \partial S)
$$

**This gives you the exact signed distance at every dose grid point, computed directly from the polygon vertices.** No rasterisation, no binary mask, no information loss. The distance from the grid point to the true contour boundary is known to floating-point precision (${\sim}10^{-15}$ m).

### The 2D computation is fully vectorisable

For a dose grid slice with $M = M_x \times M_y$ points and a contour with $N$ edges:

```python
# points: shape (M, 2)
# v0, v1: shape (N, 2) — edge start/end vertices

# Broadcast: (M, 1, 2) - (1, N, 2) → (M, N, 2)
dp = points[:, None, :] - v0[None, :, :]      # vectors from edge starts to each point
edges = v1 - v0                                 # edge vectors, shape (N, 2)

# Parameter along each edge
t = dot(dp, edges) / dot(edges, edges)          # shape (M, N)
t = clamp(t, 0, 1)

# Nearest point on each edge
nearest = v0 + t[..., None] * edges             # shape (M, N, 2)

# Distance to each edge
dist = norm(points[:, None, :] - nearest, dim=-1)  # shape (M, N)

# Minimum distance across all edges
min_dist = min(dist, dim=1)                     # shape (M,)
```

For $M = 256 \times 256 = 65{,}536$ and $N = 100$, this is 6.5M point-to-segment distances — about 10 ms in NumPy, under 1 ms on GPU. **Faster than rasterising to a supersampled binary mask.**

---

## Extending to 3D: inter-slice interpolation

RT contours are defined on discrete CT slices at heights $z_0, z_1, \ldots, z_K$. Between slices, the structure boundary is undefined — DICOM provides no inter-slice geometry. You have 2D SDFs $\phi(x, y; z_k)$ at each contour slice.

The dose grid has its own $z$-coordinates, which generally don't coincide with CT slice positions. You need $\phi$ at dose grid $z$-values.

### Linear interpolation in z

For a dose grid point at height $z$ where $z_k \leq z < z_{k+1}$:

$$
\phi(x, y, z) = (1 - \alpha)\,\phi(x, y; z_k) + \alpha\,\phi(x, y; z_{k+1})
$$

where $\alpha = (z - z_k) / (z_{k+1} - z_k)$.

This produces a smooth 3D SDF whose zero level set **linearly morphs** between the contour shapes on adjacent slices. This is physically reasonable — organ boundaries don't jump discontinuously between 2–3 mm CT slices.

### Why this is much better than binary interpolation

The alternative (binary mask, extend each slice ±half-slice-thickness) creates a staircase in z. The structure has a flat top and flat bottom with sharp steps. Linear SDF interpolation instead creates a smooth taper — the structure gradually thins as you move beyond the last contour slice, with the zero crossing (boundary) at a geometrically reasonable position.

### End-capping falls out naturally

At the superior end (above the topmost contour at $z_K$), you have $\phi(x, y; z_K)$. As $z$ increases beyond $z_K$, if you extrapolate using the SDF of the last contour with an additional distance penalty:

$$
\phi(x, y, z) = \phi(x, y; z_K) + (z - z_K) \quad \text{for } z > z_K
$$

...the zero level set curves inward and closes. This is equivalent to a hemispherical cap whose shape is determined by the contour geometry. More sophisticated approaches (Poisson reconstruction, or explicit CDT cap + SDF recomputation) are available, but this linear extrapolation is surprisingly effective and is what the Nelms test suite implicitly assumes for many test geometries.

---

## Partial-volume estimation without supersampling

Here's the payoff. You now have $\phi(i, j, k)$ — the exact signed distance from each dose grid voxel centre to the true structure boundary — at the native dose grid resolution. No supersampling was required.

### For fully interior voxels ($\phi \ll 0$)

If $|\phi(i,j,k)| > \frac{1}{2}\sqrt{\Delta x^2 + \Delta y^2 + \Delta z^2}$ (distance exceeds the half-diagonal of the voxel), the voxel cannot possibly be intersected by the boundary. The fractional volume is exactly 1 (if $\phi < 0$) or 0 (if $\phi > 0$).

### For boundary voxels: the planar approximation

When the structure surface passes through a voxel, the intersection region has a complicated shape in general. But at the scale of a single dose voxel (2.5 mm), most organ surfaces are **locally planar** — the radius of curvature of a kidney, bladder, prostate, etc. is tens of millimetres, much larger than $\Delta x$.

Under the planar approximation, the boundary within a voxel is a plane at signed distance $\phi$ from the centre, with unit normal $\hat{\mathbf{n}} = \nabla\phi / |\nabla\phi|$.

For a rectangular voxel, the fraction of volume on the negative (interior) side of a plane at signed distance $d$ from the centre, with normal direction $\hat{\mathbf{n}}$, depends on $d$ and $\hat{\mathbf{n}}$. The simplest case:

**Normal aligned with a grid axis** (e.g., $\hat{\mathbf{n}} = \hat{x}$):

$$
f = \frac{1}{2} - \frac{\phi}{\Delta x}
$$

This is exact. If $\phi = 0$ (boundary passes through the centre), $f = 0.5$. If $\phi = -\Delta x / 2$ (boundary at the far edge), $f = 1$.

**Arbitrary normal direction:**

For a plane with normal $\hat{\mathbf{n}} = (n_x, n_y, n_z)$ at signed distance $\phi$ from the voxel centre, the fractional interior volume is:

$$
f(\phi) = \frac{1}{\Delta x \Delta y \Delta z} \int\int\int_{\text{voxel}} \mathbf{1}\left[\hat{\mathbf{n}} \cdot (\mathbf{r} - \mathbf{r}_c) < -\phi\right] \, dx\, dy\, dz
$$

This integral has a closed-form solution involving the **clipped box-plane intersection volume**. For a unit cube, it's a piecewise polynomial in $\phi$ with breakpoints at $\pm n_x/2$, $\pm n_y/2$, $\pm n_z/2$, etc. The formula is given by Scardovelli & Zaleski (1999) in the Volume of Fluid literature — it's the same problem that CFD solves for tracking fluid interfaces.

The gradient $\nabla\phi$ can be estimated via central differences on the SDF grid:

$$
\frac{\partial \phi}{\partial x}\bigg|_{i,j,k} \approx \frac{\phi(i+1,j,k) - \phi(i-1,j,k)}{2\Delta x}
$$

### How good is this approximation?

The error comes from **surface curvature**. If the surface has local radius of curvature $R$, the maximum error in the planar approximation over a voxel of size $\Delta x$ is:

$$
\epsilon \sim \frac{\Delta x^2}{8R}
$$

For a 3 cm radius structure (e.g., prostate) on a 2.5 mm grid:

$$
\epsilon \sim \frac{(2.5)^2}{8 \times 30} \approx 0.026 \text{ mm} \approx 1\% \text{ of voxel width}
$$

The fractional volume error per boundary voxel is of order $\epsilon / \Delta x \sim 1\%$. Compare this to the binary method's error of up to **50% per boundary voxel**.

### Summary: accuracy hierarchy

| Method | Max error per boundary voxel | Requires supersampling? |
| -------- | ------ | ------ |
| Binary centre-point | 100% of $\Delta V$ | No (but inaccurate) |
| $k\times$ supersampled binary | $\sim 1/k^3$ of $\Delta V$ | Yes, $k^3 \times$ cost |
| SDF planar approximation | $\sim (\Delta x / R)^2$ of $\Delta V$ | **No** |
| SDF + higher-order curvature correction | $\sim (\Delta x / R)^4$ of $\Delta V$ | **No** |
| Analytical clipping (r3d) | Machine precision | **No** |

The SDF approach gets you to ~1% per-voxel accuracy at the **native grid resolution** because it preserves the sub-voxel boundary position that binary rasterisation destroys. Supersampling the binary mask is a brute-force way to recover a fraction of that information; the SDF approach recovers all of it directly.

---

## When dose varies within a boundary voxel

### Reframing the real DVH integral

Up to this point, we've treated each voxel's dose as uniform — $D(i,j,k)$ is the dose at the voxel centre, and we assign it to the entire interior portion of the voxel. The exact DVH contribution from a boundary voxel is actually:

$$
\text{contribution to } V(d) = \int_{\text{voxel} \cap S} \mathbf{1}[D(\mathbf{r}) \geq d] \, d^3r
$$

We've been approximating $D(\mathbf{r}) \approx D(\mathbf{r}_c) = \text{const}$ within the voxel, which lets us factor the integral:

$$
\approx \mathbf{1}[D(\mathbf{r}_c) \geq d] \cdot v_{ijk}
$$

This is valid when $D$ doesn't vary much across the voxel. But when does it break down?

### Quantifying intra-voxel dose variation

The dose at an arbitrary point within the voxel can be Taylor-expanded around the centre:

$$
D(\mathbf{r}) = D(\mathbf{r}_c) + \nabla D \cdot (\mathbf{r} - \mathbf{r}_c) + \frac{1}{2}(\mathbf{r} - \mathbf{r}_c)^T \mathbf{H} (\mathbf{r} - \mathbf{r}_c) + \ldots
$$

where $\nabla D$ is the dose gradient and $\mathbf{H}$ is the Hessian (curvature of the dose field). The maximum dose excursion within a voxel is:

$$
\delta D_{\max} = |\nabla D| \cdot \frac{\Delta_{\max}}{2}
$$

where $\Delta_{\max} = \sqrt{\Delta x^2 + \Delta y^2 + \Delta z^2}$ is the voxel half-diagonal.

For the uniform-dose approximation to be acceptable, we need $\delta D_{\max}$ to be small compared to the dose bin width used in the DVH, or more precisely, small compared to the dose value itself (for relative DVH accuracy).

### Clinical dose gradient magnitudes

To assess when this matters, consider representative dose gradients:

**Conventional VMAT/IMRT (e.g., prostate, H&N):**
Typical penumbral dose gradients are 3–5%/mm in the high-gradient region (field edge, 80%–20% dose). On a 2.5 mm grid:

$$
\delta D = 4\%/\text{mm} \times 1.25 \text{ mm} = 5\% \text{ of } D_{\max}
$$

This means a boundary voxel straddling a field edge could have dose varying by ~5% across its extent. For DVH bins of 1 cGy resolution, this is a meaningful variation — but it only affects the small number of boundary voxels that simultaneously sit on the structure boundary *and* in a steep dose gradient region. The probability of this double coincidence is small for typical geometries.

**SRS/SBRT (small fields, sharp penumbra):**
Dose gradients can reach 10–20%/mm with small cones or MLCs near the field edge. On a 2.5 mm grid:

$$
\delta D = 15\%/\text{mm} \times 1.25 \text{ mm} = 18.75\%
$$

Now the dose varies by nearly 20% across a single voxel. For a boundary voxel of a small brain met sitting right at the PTV edge in the penumbral region, the uniform-dose assumption is genuinely poor.

**However**: SRS/SBRT plans computed on 2.5 mm grids are themselves unreliable — clinical practice mandates dose calculation on 1.0–1.25 mm grids for small targets precisely because the TPS dose engine's own accuracy degrades. At 1.0 mm grid spacing:

$$
\delta D = 15\%/\text{mm} \times 0.5 \text{ mm} = 7.5\%
$$

This is more tolerable but still non-trivial.

**Brachytherapy:**
Near a brachytherapy source, $D \propto 1/r^2$, giving:

$$
\frac{|\nabla D|}{D} = \frac{2}{r}
$$

At $r = 5$ mm from the source on a 1 mm grid: $\delta D / D = 2/5 \times 0.5 = 20\%$. At $r = 2$ mm: $\delta D / D = 50\%$. The uniform-dose assumption collapses entirely near brachytherapy sources.

### When to worry: a quantitative criterion

Define the **dose variation ratio** for a boundary voxel:

$$
\rho = \frac{|\nabla D| \cdot \Delta_{\max}}{2 D(\mathbf{r}_c)}
$$

As a practical guide:

- $\rho < 0.02$ (2%): Uniform dose approximation is excellent. No correction needed.
- $0.02 < \rho < 0.10$: Noticeable effect on DVH, but typically smaller than the geometric partial-volume error from binary methods. SDF geometry correction is still the dominant improvement.
- $\rho > 0.10$: Dose variation within the voxel matters. Correction warranted.

For a standard VMAT plan on a 2.5 mm grid, $\rho > 0.10$ occurs only in voxels simultaneously at the structure boundary AND in the steepest part of the penumbra. This is typically a tiny fraction of boundary voxels — perhaps 1–5%. The impact on the overall DVH is small. For SRS on a 1.0 mm grid, the fraction with $\rho > 0.10$ grows but remains geometrically constrained.

### How to correct for intra-voxel dose variation

When $\rho$ is large enough to matter, the goal is to compute the integral:

$$
\int_{\text{voxel} \cap S} D(\mathbf{r}) \, d^3r
$$

rather than approximating it as $D(\mathbf{r}_c) \times v_{ijk}$. There are three approaches, in order of increasing sophistication.

#### Approach 1: Analytical correction using dose gradient (fast, first-order)

Under the planar boundary approximation, the interior region is a half-voxel bounded by a plane. The integral of a linear dose field $D(\mathbf{r}) = D_c + \nabla D \cdot (\mathbf{r} - \mathbf{r}_c)$ over this region can be computed analytically:

$$
\int_{\text{voxel} \cap S} D(\mathbf{r}) \, d^3r = D_c \cdot v_{ijk} + \nabla D \cdot \langle \mathbf{r} - \mathbf{r}_c \rangle_{\cap} \cdot v_{ijk}
$$

where $\langle \mathbf{r} - \mathbf{r}_c \rangle_{\cap}$ is the centroid offset of the interior region relative to the voxel centre. For a planar boundary, this centroid offset is a function of $\phi$ and $\hat{\mathbf{n}}$ that can be computed in closed form alongside the volume fraction. The **effective dose** for the voxel is then:

$$
\bar{D}_{ijk} = D_c + \nabla D \cdot \Delta\mathbf{r}_{\text{centroid}}
$$

where $\Delta\mathbf{r}_{\text{centroid}}$ is the displacement from voxel centre to the centroid of the voxel-structure intersection region. This shifts the dose sample point from the voxel centre to the **centroid of the interior portion** — geometrically, exactly where you'd want to evaluate dose for a representative sample.

The dose gradient $\nabla D$ is available from central differences on the dose grid (the same operation you're already doing for the SDF gradient). The centroid offset is a by-product of the Volume-of-Fluid–style box-plane clipping calculation. So this correction is essentially free once you've done the SDF partial-volume computation.

This first-order correction captures the dominant effect. The residual error is second-order in both $\Delta x / R$ (curvature) and $\Delta x \cdot |\mathbf{H}|$ (dose field curvature), making it negligible for essentially all EBRT scenarios.

#### Approach 2: Sub-voxel quadrature (moderate cost, higher order)

For the rare voxels where even the linear dose model is insufficient (e.g., brachytherapy near a source), sample dose at $N$ points within the interior region using quadrature:

$$
\bar{D}_{ijk} = \frac{1}{v_{ijk}} \sum_{n=1}^{N} w_n \cdot D(\mathbf{r}_n) \cdot \mathbf{1}[\mathbf{r}_n \in S]
$$

where $\mathbf{r}_n$ are quadrature points within the voxel and $w_n$ are weights. Crucially, **you already know which sub-voxel points are inside the structure** — the SDF gives you $\phi(\mathbf{r}_n)$ at any point, not just grid points. So containment testing at sub-voxel points is an analytical evaluation of the SDF (interpolate from the grid or, better, re-evaluate from contour edges for boundary voxels), not a fresh rasterisation.

Stratified or Sobol quasi-random sampling with 8–27 points per boundary voxel is typically sufficient. The dose values at sub-voxel points are trilinearly interpolated from the dose grid — this is the standard assumption already made by every TPS for dose reporting at off-grid points.

**This is not "supersampling" in the traditional sense.** Traditional supersampling creates a fine binary mask to determine containment, then samples dose on the fine grid. Here, containment is known analytically from the SDF, and dose is interpolated from the original grid. The sub-voxel points serve only to capture intra-voxel dose curvature, not to determine geometry. The distinction matters because:

- You only do this for boundary voxels where $\rho > 0.10$ (a tiny fraction of total voxels)
- Containment at each sub-voxel point is an $O(1)$ SDF evaluation, not a polygon test
- The number of sub-voxel samples needed is modest (8–27) because you're resolving dose smoothness, not geometric sharpness

#### Approach 3: Adaptive refinement (maximum accuracy, targeted cost)

For a reference-quality engine that must handle pathological cases (brachytherapy, sub-centimetre SRS targets), an adaptive approach is optimal:

1. Compute $\rho$ for every boundary voxel
2. If $\rho < 0.02$: use SDF partial volume with centre-point dose (Approach 0)
3. If $0.02 < \rho < 0.10$: use centroid-corrected dose (Approach 1)
4. If $\rho > 0.10$: use sub-voxel quadrature (Approach 2) with $N$ proportional to $\rho$

The beauty is that Approaches 1 and 2 are local refinements that don't affect the global data structures. The SDF grid stays at native resolution. The dose grid stays at native resolution. You just spend a few extra FLOPS on the ~1–5% of voxels that need it.

### The sharpest achievable penumbra: a worst-case bound

The physically sharpest penumbra in EBRT is set by the range of secondary electrons in water/tissue. For 6 MV photons, the lateral electronic disequilibrium region (the "electron penumbra") is approximately 5–8 mm wide (10%–90% over ~6 mm, giving a gradient of ~13%/mm). For 6 MV FFF beams, the penumbra is slightly sharper due to reduced head scatter. For 10 MV FFF, it's comparable.

The dose grid spacing sets an absolute floor on what the TPS can resolve. If the TPS computes dose on a 2.5 mm grid, it has already smoothed the dose field to that resolution — the true penumbra is convolved with the grid's sampling kernel. Any sub-voxel dose variation you try to resolve is, to some extent, already lost in the TPS calculation.

This means the worst-case $\rho$ is bounded:

$$
\rho_{\max} \approx \frac{G_{\text{penumbra}} \cdot \Delta x / 2}{D_{\text{local}}}
$$

where $G_{\text{penumbra}} \approx 13\%/\text{mm}$ for the sharpest 6 MV penumbra. At 2.5 mm grid spacing near the 50% isodose line:

$$
\rho_{\max} \approx \frac{0.13 \times 1.25}{0.50} \approx 0.33
$$

So even in the absolute worst case (boundary voxel right at the steepest part of the sharpest achievable penumbra, at the 50% isodose level), the dose variation is ~33% across the voxel. The centroid correction (Approach 1) handles most of this; sub-voxel quadrature (Approach 2) with ~8 points handles the rest. And this extreme case represents a vanishingly small fraction of total voxels.

For SRS with 1.0 mm grid spacing: $\rho_{\max} \approx 0.13 \times 0.5 / 0.5 = 0.13$ — just barely above the Approach 1 threshold, and trivially handled.

---

## Very small structures and high curvature

### The problem: when the planar approximation fails

For the SDF planar approximation, the error scales as $(\Delta x / R)^2$ where $R$ is the local radius of curvature. When $R$ approaches $\Delta x$, the approximation degrades severely because the boundary is no longer well-approximated by a plane within the voxel — it curves significantly.

Consider a 3 mm diameter brain metastasis ($R = 1.5$ mm) on a 1.0 mm dose grid (the minimum clinically appropriate for SRS). The structure spans roughly 3 voxels across. **Every voxel is a boundary voxel** — there are essentially no fully interior voxels. The curvature error:

$$
\epsilon_{\text{vol}} \sim \frac{\Delta x^2}{8R} = \frac{1.0^2}{8 \times 1.5} \approx 0.083 \text{ mm}
$$

As a fraction of voxel width: $\epsilon_{\text{vol}} / \Delta x \approx 8.3\%$ per boundary voxel. Since almost all voxels are boundary voxels, this error doesn't cancel as favourably as it does for large structures, and the cumulative DVH error could reach several percent of the total structure volume.

On a 2.5 mm grid, the situation is much worse: $R / \Delta x = 0.6$, meaning the structure radius is *smaller* than the voxel spacing. The structure fits inside a $2 \times 2 \times 2$ block of voxels. No voxelisation scheme — SDF-based or otherwise — can produce a meaningful DVH at this resolution. This is not a limitation of the algorithm; it's a fundamental sampling problem. **Clinical practice already recognises this: SRS for small brain mets requires dose calculation on ≤1.0 mm grids.**

### How many voxels span the structure? A practical threshold

The ratio $R / \Delta x$ controls everything. Let's quantify the regimes:

| $R / \Delta x$ | Structure examples | Interior voxels | SDF planar error | Assessment |
| ------ | ------ | ------ | ------ | ------ |
| $> 10$ | Bladder, liver, lung | ${\sim}95\%$+ | $< 0.1\%$ per voxel | Planar model excellent |
| $5$–$10$ | Prostate, kidney | ${\sim}85\%$ | $0.1$–$1\%$ per voxel | Planar model good |
| $2$–$5$ | Optic nerve, cochlea | ${\sim}50$–$70\%$ | $1$–$5\%$ per voxel | Curvature correction recommended |
| $1$–$2$ | 3 mm brain met (1 mm grid) | ${\sim}20$–$40\%$ | $5$–$15\%$ per voxel | Need higher-order methods |
| $< 1$ | 3 mm brain met (2.5 mm grid) | ${\sim}0\%$ | $> 15\%$ per voxel | Grid too coarse; no algorithm helps |

### Quadratic curvature correction

The next step beyond the planar approximation is to model the boundary as a **quadric surface** within each voxel. If the surface has principal curvatures $\kappa_1$ and $\kappa_2$ (with $\kappa = 1/R$), the local surface within a voxel centred at signed distance $\phi$ from the boundary can be written in a local coordinate frame as:

$$
z = -\phi + \frac{1}{2}\kappa_1 x^2 + \frac{1}{2}\kappa_2 y^2
$$

The volume of a rectangular voxel below this quadric surface has a closed-form expression involving the error function (for the Gaussian-like curvature terms). The correction to the planar volume fraction is:

$$
\Delta f = -\frac{\kappa_1 \Delta x^2 + \kappa_2 \Delta y^2}{24} + O(\kappa^2 \Delta x^4)
$$

The curvatures can be estimated from the SDF's second derivatives (the Hessian of $\phi$):

$$
\kappa = \nabla \cdot \hat{\mathbf{n}} = \nabla \cdot \frac{\nabla \phi}{|\nabla \phi|}
$$

In practice, this is computed via finite differences on the SDF grid. The mean curvature $H = (\kappa_1 + \kappa_2)/2$ is:

$$
H = \frac{\phi_{xx}(\phi_y^2 + \phi_z^2) + \phi_{yy}(\phi_x^2 + \phi_z^2) + \phi_{zz}(\phi_x^2 + \phi_y^2) - 2(\phi_x \phi_y \phi_{xy} + \phi_x \phi_z \phi_{xz} + \phi_y \phi_z \phi_{yz})}{2|\nabla\phi|^3}
$$

This is the standard expression used in level-set methods and computational fluid dynamics. It gives the curvature correction at every boundary voxel from the same SDF data you already have.

**For the 3 mm brain met on a 1 mm grid**: the quadratic correction reduces the per-voxel error from ~8% to ~0.5%, which is comparable to the planar model's performance on large structures. The cost is computing second derivatives of $\phi$ — a 3×3×3 stencil operation — only at boundary voxels.

### Exact analytical clipping for the demanding case

When even the quadratic correction isn't enough (extremely small structures, or when you need machine-precision reference values for validation), **exact polyhedron-voxel intersection** is the gold standard.

The idea: construct the actual polygon (or polyhedron) representing the structure boundary within each voxel, clip it against the voxel faces using Sutherland-Hodgman clipping, and compute the enclosed volume analytically.

For the 2D-per-slice case that RT contours naturally provide, this is particularly tractable:

1. For each CT slice, clip the contour polygon against each voxel's 2D bounding box
2. Compute the area of the clipped polygon (using the shoelace formula — exact)
3. Between slices, linearly interpolate the clipped areas to get volume contributions

The clipping is $O(N)$ per polygon edge per voxel, but only boundary voxels need it. For a 3 mm met on a 1 mm grid, there are ~80 boundary voxels per slice and ~3 slices, so ~240 clip operations — trivial.

The **r3d library** (Powell & Abel, J. Comp. Physics 2015) generalises this to full 3D polyhedron-voxel intersection with machine-precision accuracy (${\sim}10^{-14}$ relative error). It computes volumes and moments (including first moments, which give the centroid for dose correction) via recursive vertex enumeration. For a reference-quality DVH engine, r3d provides the ground truth against which faster methods can be validated.

### A tiered architecture for all structure sizes

The practical solution is to dispatch per-voxel based on the local geometry:

```plaintext
For each boundary voxel (i, j, k):

    # Estimate local curvature from SDF Hessian
    κ = compute_mean_curvature(φ, i, j, k)

    # Compute dose variation ratio
    ρ = |∇D| * Δ_max / (2 * D_c)

    # Dispatch
    if |κ| * Δx < 0.1:
        # Large structure regime: planar model
        f = planar_volume_fraction(φ, ∇φ, Δx, Δy, Δz)
        D_eff = D_c  (or centroid-corrected if ρ > 0.02)

    elif |κ| * Δx < 0.5:
        # Medium structure regime: quadratic correction
        f = planar_volume_fraction(...) + curvature_correction(κ, Δx, Δy, Δz)
        D_eff = centroid_corrected_dose(D_c, ∇D, centroid_offset)

    else:
        # Small structure regime: exact clipping
        f = exact_polygon_voxel_intersection(contour, voxel_bounds)
        D_eff = subvoxel_quadrature(D_grid, interior_region, N=8)
```

The vast majority of voxels (>95% for typical clinical cases) take the fast planar path. The quadratic path handles medium-curvature cases with minimal overhead (one Hessian computation per voxel). The exact clipping path is reserved for the genuinely hard cases — small brain mets, thin tubular structures like the optic nerve — where it's both necessary and affordable because the structure itself contains very few voxels.

This dispatch costs essentially nothing — you're computing the SDF Hessian (a 3×3×3 stencil) only at boundary voxels, and using the curvature value you already need for the quadratic correction to decide whether to invoke the exact clipper.

---

## Worked example: 1D illustration

Consider a 1D "voxel" from $x = 0$ to $x = \Delta x = 2.5$ mm. The structure boundary is at $x_b = 1.8$ mm (known exactly from the contour vertex interpolation). The dose is $D = 60$ Gy uniform across the voxel (for simplicity).

**Binary method:** The voxel centre is at $x_c = 1.25$ mm. Since $x_c < x_b$, the centre is inside, so $v = \Delta x = 2.5$ mm. Actual interior length: $1.8$ mm. **Error: +0.7 mm (+39%).**

**4× supersampled binary:** Sub-centres at 0.3125, 0.9375, 1.5625, 2.1875 mm. The first three are inside ($< 1.8$), so $v = 3/4 \times 2.5 = 1.875$ mm. **Error: +0.075 mm (+4.2%).**

**SDF method:** $\phi(x_c) = x_c - x_b = 1.25 - 1.8 = -0.55$ mm (negative = inside). Fractional volume $= 1/2 - \phi/\Delta x = 0.5 + 0.55/2.5 = 0.72$. So $v = 0.72 \times 2.5 = 1.8$ mm. **Error: 0. Exact.**

The SDF method is exact in 1D because the boundary *is* planar (it's a point). In 2D and 3D with curved boundaries, it's approximate but the error is controlled by the curvature term derived above.

### Extended 1D example: non-uniform dose

Same geometry, but now dose varies linearly: $D(x) = 60 + 4(x - x_c)$ Gy (a gradient of 4 Gy/mm, steep but not extreme).

**Binary centre-point method:** Reports $D = 60$ Gy for the entire voxel, volume $= 2.5$ mm. Dose-volume contribution: 60 Gy × 2.5 mm.

**True integral:** $\int_0^{1.8} D(x)\, dx = \int_0^{1.8} [60 + 4(x - 1.25)]\, dx$. Evaluating: $= [60x + 2x^2 - 5x]_0^{1.8} = [55x + 2x^2]_0^{1.8} = 55(1.8) + 2(1.8)^2 = 99 + 6.48 = 105.48$ Gy·mm.

**SDF + centroid correction:** Interior fraction $= 0.72$, volume $= 1.8$ mm. Interior centroid at $x = 1.8/2 = 0.9$ mm. Dose at centroid: $D(0.9) = 60 + 4(0.9 - 1.25) = 58.6$ Gy. Dose-volume contribution: $58.6 \times 1.8 = 105.48$ Gy·mm. **Exact.** (Because the dose is linear and the geometry is 1D — the centroid correction is sufficient for linear dose fields.)

---

## The complete algorithm

```plaintext
For each structure S:
    For each CT slice k that has a contour for S:
        For each dose grid point (x_i, y_j) on this slice:
            Compute exact 2D signed distance φ(i,j,k)
            to the contour polygon (vectorised over all edges)

    For each dose grid z-plane:
        Interpolate φ from bracketing CT slices (linear in z)

    Classify every voxel:
        |φ| > half_diagonal  →  fully interior (φ < 0) or exterior (φ > 0)
        otherwise  →  boundary voxel

    For each boundary voxel (i,j,k):
        Compute ∇φ via central differences  →  surface normal n̂
        Compute mean curvature κ from SDF Hessian (if needed)
        Compute dose gradient ∇D via central differences
        Compute ρ = |∇D| · Δ_max / (2 · D_c)

        # Geometry: select accuracy tier
        if |κ| · Δx < 0.1:
            f = planar_volume_fraction(φ, n̂, Δx, Δy, Δz)
        elif |κ| · Δx < 0.5:
            f = planar_fraction + curvature_correction(κ, Δx, Δy, Δz)
        else:
            f = exact_polygon_clip(contour, voxel_bounds)

        # Dose: select accuracy tier
        if ρ < 0.02:
            D_eff = D(i,j,k)                        # centre-point dose
        elif ρ < 0.10:
            D_eff = D(i,j,k) + ∇D · Δr_centroid    # centroid-corrected
        else:
            D_eff = subvoxel_quadrature(D_grid, interior_region, N=8)

        v[i,j,k] = f × ΔV
        dose_eff[i,j,k] = D_eff

    For interior voxels:
        v[i,j,k] = ΔV
        dose_eff[i,j,k] = D(i,j,k)

    V_total = sum(v)

    For each dose bin d:
        DVH(d) = sum(v[i,j,k] where dose_eff[i,j,k] ≥ d) / V_total
```

**No global supersampling of anything.** The geometry is exact from the contours. The dose is smooth and needs correction only at the small fraction of voxels where steep gradients coincide with structure boundaries. The tiered dispatch concentrates computational effort exactly where it's needed — at the geometric and dosimetric boundaries where accuracy matters most.
