"""Newton Raphson Geometry

The Newton Raphson geometry represents a surface utilizing the Newton-Raphson
method for ray tracing. This is an abstract base class that should be inherited
by any geometry that uses the Newton-Raphson method for ray tracing.

Kramer Harrison, 2024
"""

import warnings
from abc import ABC, abstractmethod

import optiland.backend as be
from optiland.coordinate_system import CoordinateSystem
from optiland.geometries.standard import StandardGeometry


# -- utility functions --
def _is_radius_infinite(radius):
    """Checks if the given radius represents an infinite radius (a plane).

    Args:
        radius (float or be.ndarray): The radius value to check.

    Returns:
        bool: True if the radius is effectively infinite (or all elements are
        infinite if it's an array), False otherwise.
    """
    is_inf_tensor = be.isinf(radius)
    if hasattr(is_inf_tensor, "ndim") and is_inf_tensor.ndim > 0:
        # If it's a multi-element array, check if all are infinite
        return bool(be.all(is_inf_tensor))
    # For scalars or single-element arrays that can be converted by .item()
    return (
        bool(is_inf_tensor.item())
        if hasattr(is_inf_tensor, "item")
        else bool(is_inf_tensor)
    )


class NewtonRaphsonGeometry(StandardGeometry, ABC):
    """Represents a geometry that uses the Newton-Raphson method for ray tracing.

    Args:
        coordinate_system (CoordinateSystem): The coordinate system of the geometry.
        radius (float): The radius of curvature of the base sphere.
        conic (float, optional): The conic constant of the base sphere.
            Defaults to 0.0.
        tol (float, optional): Tolerance for Newton-Raphson iteration.
            Defaults to 1e-10.
        max_iter (int, optional): Maximum iterations for Newton-Raphson.
            Defaults to 100.

    """

    def __init__(self, coordinate_system, radius, conic=0.0, tol=1e-10, max_iter=100):
        super().__init__(coordinate_system, radius, conic)
        self.tol = tol
        self.max_iter = max_iter

    def __str__(self):
        return "Newton Raphson"  # pragma: no cover

    def flip(self):
        """Flip the geometry.

        Changes the sign of the radius of curvature.
        The conic constant remains unchanged.
        """
        self.radius = -self.radius

    @abstractmethod
    def sag(self, x=0, y=0):
        """Calculate the surface sag of the geometry.

        Args:
            x (float or be.ndarray, optional): The x-coordinate(s). Defaults to 0.
            y (float or be.ndarray, optional): The y-coordinate(s). Defaults to 0.

        Returns:
            float or be.ndarray: The surface sag of the geometry at the given
            coordinates.

        """
        # pragma: no cover

    @abstractmethod
    def _surface_normal(self, x, y):
        """Calculate the surface normal of the geometry at the given x and y
        position.

        Args:
            x (be.ndarray): The x-coordinate(s) at which to calculate the normal.
            y (be.ndarray): The y-coordinate(s) at which to calculate the normal.

        Returns:
            tuple[be.ndarray, be.ndarray, be.ndarray]: The surface normal
            components (nx, ny, nz).

        """
        # pragma: no cover

    def surface_normal(self, rays):
        """Calculates the surface normal of the geometry at the given rays.

        Args:
            rays (RealRays): The rays, positioned at the surface, for which to
                calculate the surface normal.

        Returns:
            tuple[be.ndarray, be.ndarray, be.ndarray]: The surface normal
            components (nx, ny, nz).

        """
        return self._surface_normal(rays.x, rays.y)

    def distance(self, rays):
        """Calculates the distance between the geometry and the given ray
        positions.

        Note:
            This function uses the Newton-Raphson method for ray tracing.

        Args:
            rays (RealRays): The rays used for calculating distance.

        Returns:
            be.ndarray: An array of distances from each ray's current position
            to its intersection point with the geometry.

        """
        x, y, z = self._intersection(rays)
        intersections = be.column_stack((x, y, z))
        ray_directions = be.column_stack((rays.L, rays.M, rays.N))

        for _ in range(self.max_iter):
            z_surface = self.sag(intersections[:, 0], intersections[:, 1])
            dz = intersections[:, 2] - z_surface
            distance = dz / ray_directions[:, 2]
            intersections = intersections - distance[:, None] * ray_directions
            if be.max(be.abs(dz)) < self.tol:
                break

        position = be.column_stack((rays.x, rays.y, rays.z))
        return be.linalg.norm(intersections - position, axis=1)

    def _intersection_plane(self, rays):
        """Calculates the intersection points of the rays with a plane (z=0).

        Args:
            rays (RealRays): The rays to calculate the intersection points for.

        Returns:
            tuple[be.ndarray, be.ndarray, be.ndarray]: The x, y, and z
            coordinates of the intersection points.
        """
        # handle infinite radius: intersection with plane z=0
        t = be.full_like(rays.z, be.nan)

        # rays not parallel to the XY plane (N != 0)
        mask_N_nonzero = be.abs(rays.N) > self.tol

        t = be.where(mask_N_nonzero, -rays.z / rays.N, t)

        mask_N_zero_and_z_zero = (~mask_N_nonzero) & (be.abs(rays.z) < self.tol)
        t = be.where(mask_N_zero_and_z_zero, 0.0, t)

        x = rays.x + rays.L * t
        y = rays.y + rays.M * t
        z = rays.z + rays.N * t

        return x, y, z

    def _intersection_sphere(self, rays):
        """Calculates the intersection points of the rays with the geometry.

        Args:
            rays (RealRays): The rays to calculate the intersection points for.

        Returns:
            tuple[be.ndarray, be.ndarray, be.ndarray]: The x, y, and z
            coordinates of the intersection points.

        """
        a = rays.L**2 + rays.M**2 + rays.N**2
        b = (
            2 * rays.L * rays.x
            + 2 * rays.M * rays.y
            - 2 * rays.N * self.radius
            + 2 * rays.N * rays.z
        )
        c = rays.x**2 + rays.y**2 + rays.z**2 - 2 * self.radius * rays.z

        # discriminant
        d = b**2 - 4 * a * c

        # two solutions for distance to sphere
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            t1 = (-b + be.sqrt(d)) / (2 * a)
            t2 = (-b - be.sqrt(d)) / (2 * a)

        # find intersection points in z
        z1 = rays.z + t1 * rays.N
        z2 = rays.z + t2 * rays.N

        # take intersection closest to z = 0 (i.e., vertex of geometry)
        t = be.where(be.abs(z1) <= be.abs(z2), t1, t2)

        # handle case when a = 0
        cond = a == 0
        t[cond] = -c[cond] / b[cond]

        x = rays.x + rays.L * t
        y = rays.y + rays.M * t
        z = rays.z + rays.N * t

        return x, y, z

    def _intersection(self, rays):
        """Calculates the initial intersection points of the rays with the base
        geometry (sphere or plane) before Newton-Raphson iteration.

        Args:
            rays (RealRays): The rays to calculate the intersection points for.

        Returns:
            tuple[be.ndarray, be.ndarray, be.ndarray]: The x, y, and z
            coordinates of the initial intersection points.
        """
        if _is_radius_infinite(self.radius):
            return self._intersection_plane(rays)
        else:
            return self._intersection_sphere(rays)

    def to_dict(self):
        """Converts the geometry to a dictionary.

        Returns:
            dict: The dictionary representation of the geometry.

        """
        geometry_dict = super().to_dict()
        geometry_dict.update({"tol": self.tol, "max_iter": self.max_iter})
        return geometry_dict

    @classmethod
    def from_dict(cls, data):  # pragma: no cover
        """Creates a geometry from a dictionary representation.

        Args:
            data (dict): The dictionary representation of the geometry.

        Returns:
            NewtonRaphsonGeometry: An instance of a subclass of
            NewtonRaphsonGeometry, created from the dictionary data.

        """
        required_keys = {"cs", "radius"}
        if not required_keys.issubset(data):
            missing = required_keys - data.keys()
            raise ValueError(f"Missing required keys: {missing}")

        cs = CoordinateSystem.from_dict(data["cs"])
        conic = data.get("conic", 0.0)
        tol = data.get("tol", 1e-10)
        max_iter = data.get("max_iter", 100)

        return cls(cs, data["radius"], conic, tol, max_iter)
