"""Point Spread Function (PSF) Module

This module provides functionality for simulating and analyzing the Pointp
spread function (PSF) of optical systems using the Fast Fourier Transform
(FFT). It includes capabilities for generating PSF from given wavefront
aberrations, visualizing the PSF in both 2D and 3D projections, and
calculating the Strehl ratio, which is a measure of the quality of an optical
system.

Kramer Harrison, 2023
"""

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from matplotlib.colors import LogNorm
from scipy.ndimage import zoom

import optiland.backend as be
from optiland.wavefront import Wavefront


class FFTPSF(Wavefront):
    """Class representing the Fast Fourier Transform (FFT)
    Point Spread Function (PSF).

    Args:
        optic (Optic): The optical system.
        field (tuple): The field as (x, y) at which to compute the PSF.
        wavelength (float): The wavelength of light.
        num_rays (int, optional): The number of rays used for computing the
            PSF. Defaults to 128.
        grid_size (int, optional): The size of the grid used for computing the
            PSF. Defaults to 1024.

    Attributes:
        grid_size (int): The size of the grid used for computing the PSF.
        pupils (list): The list of pupil functions, as generated by
            wavefront.Wavefront.
        psf (ndarray): The computed PSFs.

    Methods:
        view(projection='2d', log=False, figsize=(7, 5.5), threshold=0.05,
            num_points=128): Visualizes the PSF.
        strehl_ratio(): Computes the Strehl ratio of the PSF.

    """

    def __init__(self, optic, field, wavelength, num_rays=128, grid_size=1024):
        super().__init__(
            optic=optic,
            fields=[field],
            wavelengths=[wavelength],
            num_rays=num_rays,
            distribution="uniform",
        )

        self.grid_size = grid_size
        self.pupils = self._generate_pupils()
        self.psf = self._compute_psf()

    def view(
        self,
        projection="2d",
        log=False,
        figsize=(7, 5.5),
        threshold=0.05,
        num_points=128,
    ):
        """Visualizes the PSF.

        Args:
            projection (str, optional): The projection type. Can be '2d' or
                '3d'. Defaults to '2d'.
            log (bool, optional): Whether to use a logarithmic scale for the
                intensity. Defaults to False.
            figsize (tuple, optional): The figure size. Defaults to (7, 5.5).
            threshold (float, optional): The threshold for determining the
                bounds of the PSF. Defaults to 0.05.
            num_points (int, optional): The number of points used for
                interpolating the PSF. Defaults to 128.

        Raises:
            ValueError: If the projection is not '2d' or '3d'.

        """
        psf = be.to_numpy(self.psf)
        min_x, min_y, max_x, max_y = self._find_bounds(psf, threshold)
        psf_zoomed = psf[min_x:max_x, min_y:max_y]
        x_extent, y_extent = self._get_psf_units(psf_zoomed)
        psf_smooth = self._interpolate_psf(psf_zoomed, num_points)

        if projection == "2d":
            self._plot_2d(psf_smooth, log, x_extent, y_extent, figsize=figsize)
        elif projection == "3d":
            self._plot_3d(psf_smooth, log, x_extent, y_extent, figsize=figsize)
        else:
            raise ValueError('OPD projection must be "2d" or "3d".')

    def strehl_ratio(self):
        """Computes the Strehl ratio of the PSF.

        Returns:
            float: The Strehl ratio.

        """
        return self.psf[self.grid_size // 2, self.grid_size // 2] / 100

    def _plot_2d(self, image, log, x_extent, y_extent, figsize=(7, 5.5)):
        """Plot the PSF in 2d.

        Args:
            image (numpy.ndarray): The 2D image of the PSF to plot..
            log (bool): If True, apply logarithmic normalization to the image.
            x_extent (float): The extent of the x-axis.
            y_extent (float): The extent of the y-axis.
            figsize (tuple, optional): The size of the figure.
                Defaults to (7, 5.5).

        """
        _, ax = plt.subplots(figsize=figsize)
        norm = LogNorm() if log else None

        # replace values <= 0 with smallest non-zero value in image
        image[image <= 0] = np.min(image[image > 0])

        extent = [-x_extent / 2, x_extent / 2, -y_extent / 2, y_extent / 2]
        im = ax.imshow(image, norm=norm, extent=extent)

        ax.set_xlabel("X (µm)")
        ax.set_ylabel("Y (µm)")
        ax.set_title("FFT PSF")

        cbar = plt.colorbar(im)
        cbar.ax.get_yaxis().labelpad = 15
        cbar.ax.set_ylabel("Relative Intensity (%)", rotation=270)
        plt.show()

    def _plot_3d(self, image, log, x_extent, y_extent, figsize=(7, 5.5)):
        """Plot the PSF in 3d.

        Args:
            image (ndarray): The PSF image data.
            log (bool): Whether to apply logarithmic scaling to the image.
            x_extent (float): The extent of the x-axis.
            y_extent (float): The extent of the y-axis.
            figsize (tuple, optional): The size of the figure.
                Defaults to (7, 5.5).

        """
        fig, ax = plt.subplots(subplot_kw={"projection": "3d"}, figsize=figsize)

        x = np.linspace(-x_extent / 2, x_extent / 2, image.shape[1])
        y = np.linspace(-y_extent / 2, y_extent / 2, image.shape[0])
        X, Y = np.meshgrid(x, y)

        # replace values <= 0 with smallest non-zero value in image
        image[image <= 0] = np.min(image[image > 0])

        log_formatter = None
        if log:
            image = np.log10(image)
            formatter = mticker.FuncFormatter(self._log_tick_formatter)
            ax.zaxis.set_major_formatter(formatter)
            ax.zaxis.set_major_locator(mticker.MaxNLocator(integer=True))
            log_formatter = self._log_colorbar_formatter

        surf = ax.plot_surface(
            X,
            Y,
            image,
            rstride=1,
            cstride=1,
            cmap="viridis",
            linewidth=0,
            antialiased=False,
        )

        ax.set_xlabel("X (µm)")
        ax.set_ylabel("Y (µm)")
        ax.set_zlabel("Relative Intensity (%)")
        ax.set_title("FFT PSF")

        fig.colorbar(surf, ax=ax, shrink=0.5, aspect=10, pad=0.15, format=log_formatter)
        fig.tight_layout()
        plt.show()

    def _log_tick_formatter(self, value, pos=None):
        """Format the tick labels for a logarithmic scale.

        Args:
            value (float): The tick value.
            pos (int, optional): The position of the tick.

        Returns:
            str: The formatted tick label.

        References:
            https://stackoverflow.com/questions/3909794/plotting-mplot3d-axes3d-xyz-surface-plot-with-log-scale

        """
        return f"$10^{{{int(value)}}}$"

    def _log_colorbar_formatter(self, value, pos=None):
        """Formats the tick labels for a logarithmic colorbar.

        Args:
            value (float): The tick value.
            pos (int, optional): The position of the tick.

        Returns:
            str: The formatted tick label.

        """
        linear_value = 10**value
        return f"{linear_value:.1e}"

    def _generate_pupils(self):
        """Generate the pupils for each wavelength. Utilizes wavefront.Wavefront.

        Returns:
            list: A list of complex arrays representing the pupils for each
                wavelength.

        """
        x = be.linspace(-1, 1, self.num_rays)
        x, y = be.meshgrid(x, x)
        x = x.ravel()
        y = y.ravel()
        R = be.sqrt(x**2 + y**2)

        pupils = []

        for k in range(len(self.wavelengths)):
            P = be.to_complex(be.zeros_like(x))
            amplitude = self.data[0][k][1] / be.mean(self.data[0][k][1])
            P[R <= 1] = be.to_complex(
                amplitude * be.exp(1j * 2 * be.pi * self.data[0][k][0])
            )
            P = be.reshape(P, (self.num_rays, self.num_rays))
            pupils.append(P)

        return pupils

    def _compute_psf(self):
        """Compute the Point Spread Function (PSF) for the given optical system.

        Returns:
            be.ndarray: The computed PSF as a 2D numpy array.

        """
        # TODO: add ability to compute polychromatic PSF.
        # Interpolate for each wavelength, then incoherently sum.
        pupils = self._pad_pupils()
        norm_factor = self._get_normalization()

        psf = []
        for pupil in pupils:
            amp = be.fft.fftshift(be.fft.fft2(pupil))
            psf.append(amp * be.conj(amp))
        psf = be.stack(psf)

        return be.real(be.sum(psf, axis=0)) / norm_factor * 100

    def _interpolate_psf(self, image, n=128):
        """Interpolates the point spread function (PSF) of an image. Used for
            visualization purposes only.

        Args:
            image (numpy.ndarray): The input image.
            n (int, optional): The number of points in the interpolated PSF
                grid. Default is 128.

        Returns:
            numpy.ndarray: The interpolated PSF grid.

        """
        zoom_factor = n / image.shape[0]

        if zoom_factor == 1:
            return image
        return zoom(image, zoom_factor, order=3)

    @staticmethod
    def _find_bounds(psf, threshold=0.25):
        """Finds the bounding box coordinates for the non-zero elements in the
        PSF matrix.

        Args:
            psf (numpy.ndarray): The PSF matrix.
            threshold (float): The threshold value for determining non-zero
                elements in the PSF matrix. Default is 0.25.

        Returns:
            tuple: A tuple containing the minimum and maximum x and y
                coordinates of the bounding box.

        """
        thresholded_psf = psf > threshold
        non_zero_indices = np.argwhere(thresholded_psf)

        try:
            min_x, min_y = np.min(non_zero_indices, axis=0)
            max_x, max_y = np.max(non_zero_indices, axis=0)
        except ValueError:
            min_x, min_y = 0, 0
            max_x, max_y = psf.shape

        size = max(max_x - min_x, max_y - min_y)

        peak_x, peak_y = psf.shape[0] // 2, psf.shape[1] // 2

        min_x = peak_x - size / 2
        max_x = peak_x + size / 2
        min_y = peak_y - size / 2
        max_y = peak_y + size / 2

        min_x = max(0, min_x)
        min_y = max(0, min_y)
        max_x = min(psf.shape[0], max_x)
        max_y = min(psf.shape[1], max_y)

        return int(min_x), int(min_y), int(max_x), int(max_y)

    def _pad_pupils(self):
        """Pad the pupils with zeros to match the grid size.

        Returns:
            list: A list of padded pupils.

        """
        pupils_padded = []
        for pupil in self.pupils:
            pad = (self.grid_size - pupil.shape[0]) // 2
            pupil = be.pad(
                pupil,
                ((pad, pad), (pad, pad)),
                mode="constant",
                constant_values=0,
            )
            pupils_padded.append(pupil)
        return pupils_padded

    def _get_normalization(self):
        """Calculate the normalization factor for the Point Spread Function (PSF).

        Returns:
            float: The normalization factor for the PSF.

        """
        P_nom = be.copy(self.pupils[0])
        P_nom[P_nom != 0] = 1

        amp_norm = be.fft.fftshift(be.fft.fft2(P_nom))
        psf_norm = amp_norm * be.conj(amp_norm)
        return be.max(be.real(psf_norm)) * len(self.pupils)

    def _get_psf_units(self, image):
        """Calculate the physical units of the point spread function (PSF) based
        on the given image.

        Args:
            image (numpy.ndarray): The input PSF image.

        Returns:
            tuple: A tuple containing the physical units of the PSF in the
                x and y directions.

        References:
            https://www.strollswithmydog.com/wavefront-to-psf-to-mtf-physical-units/#iv

        """
        FNO = self.optic.paraxial.FNO()

        if not self.optic.object_surface.is_infinite:
            D = self.optic.paraxial.XPD()
            p = D / self.optic.paraxial.EPD()
            m = self.optic.paraxial.magnification()
            FNO = FNO * (1 + be.abs(m) / p)

        Q = self.grid_size / self.num_rays
        dx = self.wavelengths[0] * FNO / Q

        x = be.to_numpy(image.shape[1] * dx)
        y = be.to_numpy(image.shape[0] * dx)

        return x, y
