class DeliveryDataMuDensityMixin:
    def mudensity(self, gantry_angles=None, gantry_tolerance=None,
                  grid_resolution=1, output_always_list=False):
        if gantry_angles is None:
            gantry_angles = 0
            gantry_tolerance = 500
        elif gantry_tolerance is None:
            gantry_tolerance = gantry_tol_from_gantry_angles(gantry_angles)

        masked_by_gantry = self.mask_by_gantry(gantry_angles, gantry_tolerance)

        mudensities = []
        for delivery_data in masked_by_gantry:
            mudensities.append(calc_mu_density(
                delivery_data.monitor_units,
                delivery_data.mlc,
                delivery_data.jaw,
                grid_resolution=grid_resolution))

        if not output_always_list:
            if len(mudensities) == 1:
                return mudensities[0]

        return mudensities
