# Module to calculate a DEM of difference with the consideration of a a lOD95 based on precision maps and roughness.
import sys
import os
import rasterio
from rasterio.enums import Resampling
import tempfile
from rasterio.crs import CRS
import numpy as np
import warnings
from sfm_gridz.mask_AOI import mask_it

def dem_of_diff(raster_1, raster_2, prec_point_cloud_1, prec_point_cloud_2, out_ras, epsg_code, reg_error, t_value,
                handle_gaps, mask, lod_method):
    print("calculating DEM of difference...")

    if epsg_code is not None:
        epsg_code = CRS.from_epsg(epsg_code)

    dem_od_process = deom_od(raster_1, raster_2, epsg_code, prec_point_cloud_1, prec_point_cloud_2, out_ras, reg_error,
                             t_value, handle_gaps, mask, lod_method)

    dem_od_process.load_rasters()
    dem_od_process.resample_rasters()
    dem_od_process.run_raster_calcs()
    dem_od_process.close_rasterios()
    dem_od_process.remove_temps()

    return dem_od_process


class deom_od:
    def __init__(self, rast1, rast2, epsg_c, prec_ras1, prec_ras2, out_ras_p, r_err, t_val, gap_handle, maskit, method):
        self.raster_pths = [rast1, rast2, prec_ras1, prec_ras2]
        self.rasters = [None, None, None, None]
        self.ras_out_path = out_ras_p
        self.epsg = epsg_c
        self.temp_log = []
        self.out_meta_data = None
        self.mask = maskit
        self.reg_error = r_err
        self.t_value = t_val

        if gap_handle is False:
            self.prec_band = 2
        else:
            self.prec_band = 1

        self.lod_method = method

    def load_rasters(self):

        self.rasters[0] = rasterio.open(self.raster_pths[0], 'r+')
        self.rasters[1] = rasterio.open(self.raster_pths[1], 'r+')
        self.rasters[2] = rasterio.open(self.raster_pths[2], 'r+')
        self.rasters[3] = rasterio.open(self.raster_pths[3], 'r+')

    def resample_rasters(self):

        print("resampling raster to equalise all arrays...")
        res_list = []
        for i in self.rasters:
            x_res = (i.bounds[2] - i.bounds[0]) / i.width
            y_res = (i.bounds[3] - i.bounds[1]) / i.height

            res_list.append((x_res, y_res))
        min_res = min(res_list)

        for idx, i in enumerate(self.rasters):
            x_res = (i.bounds[2] - i.bounds[0]) / i.width
            y_res = (i.bounds[3] - i.bounds[1]) / i.height

            if (x_res, y_res) != min_res:
                print("resizing rasters")

                out_meta = i.meta.copy()

                x_res_factor = x_res / min_res[0]
                y_res_factor = y_res / min_res[1]

                # resample data to target shape
                data = i.read(
                    out_shape=(
                        i.count,
                        int(i.width * x_res_factor),
                        int(i.height * y_res_factor)
                    ),
                    resampling=Resampling.bilinear)

                trans = i.transform * i.transform.scale(
                    (i.width / data.shape[-2]),
                    (i.height / data.shape[-1])
                )

                out_meta.update(
                    {"driver": "GTiff", "height": data.shape[2], "width": data.shape[1], "transform": trans,
                     "crs": self.epsg, "compress": "lzw", "nodata": -999})
                temp_ras = tempfile.NamedTemporaryFile(suffix=".tif").name

                with rasterio.open(temp_ras, "w", **out_meta) as dest:
                    dest.write(data)

                self.rasters[idx] = rasterio.open(temp_ras)

                self.temp_log.append(temp_ras)

        # function to return the index of the smallest raster
        def rasNum(ras_list):
            size_list = []
            for i in ras_list:
                n = i.shape[0]*i.shape[1]
                size_list.append(n)
            rasi = size_list.index(min(size_list))
            sras_shp = ras_list[rasi].shape
            return rasi, sras_shp

        ras_i, s_ras = rasNum(self.rasters)

        self.out_meta_data = self.rasters[ras_i].meta.copy()

        """This section below resizes arrays that don't match the dimensions of the smallest raster"""
        if (len(set([i.shape for i in self.rasters])) <= 1) is False: # checks if dims of rasters are not equal

            for idx, x in enumerate(self.rasters):
                if x.shape != s_ras:

                    diff = tuple(x - y for x, y in zip(x.shape, s_ras))

                    def reshape_arr(b_arr, difference):
                        if difference[0] > 0:
                            b_arr = np.delete(b_arr, (range(0, difference[0])), axis=0)
                        else:
                            ins_list = []
                            for i in range(0, abs(difference[0])):
                                ins_list.append(0)
                            b_arr = np.insert(b_arr, ins_list, -999, axis=0)
                        if difference[1] > 0:
                            b_arr = np.delete(b_arr, (range(b_arr.shape[-1] - (difference[1]), b_arr.shape[-1])),
                                              axis=1)
                        else:
                            ind = b_arr.shape[1]
                            ins_list = []
                            for i in range(0, abs(difference[1])):
                                ins_list.append(ind)
                            b_arr = np.insert(b_arr, ins_list, -999, axis=1)

                        return b_arr.astype('float32')

                    temp_ras = tempfile.NamedTemporaryFile(suffix=".tif").name

                    with rasterio.open(temp_ras, "w", **self.out_meta_data) as dest:
                        dest.write_band(1, reshape_arr(x.read(1), diff))
                        dest.write_band(2, reshape_arr(x.read(2), diff))

                    self.rasters[idx] = rasterio.open(temp_ras)
                    self.temp_log.append(temp_ras)

    def run_raster_calcs(self):

        """The Definitions of values are given below

        a – CLOUD1 SfM Precision
        b – DEM1 
        c – DEM1 roughness
        d – CLOUD2 SfM Precision
        e – DEM2
        f – DEM2 roughness
        g – REGISTRATION/ALIGNMENT RMSE
        """

        a = self.rasters[2].read(self.prec_band)
        a[a == -999] = np.nan
        b = self.rasters[0].read(1)
        b[b == -999] = np.nan
        c = self.rasters[0].read(2)
        c[c == -999] = np.nan
        d = self.rasters[3].read(self.prec_band)
        d[d == -999] = np.nan
        e = self.rasters[1].read(1)
        e[e == -999] = np.nan
        f = self.rasters[1].read(2)
        f[f == -999] = np.nan
        g = self.reg_error

        t = self.t_value  # could also use 1.96

        # Classic LoD - most robust appraoch
        rob_lod = t * ((a + c)**2 + (d + f)**2)**0.5 + g

        # Lod with Precision only
        # prec_lod = t * (a**2 + d**2 + g**2)**0.5  # NOT USED FOR NOW POTENTIALLY USEFUL FOR OTHER APPLICATIONS?
        # rand_noise = np.random.normal(2, 0.5, (a.shape)) #  for testing
        diff_arr = e - b  # dem of difference

        def get_dod(lod):
            dod = np.zeros(diff_arr.shape)

            warnings.filterwarnings('ignore')
            mask1 = (abs(diff_arr) > lod) & (diff_arr < 0)
            dod[mask1] = diff_arr[mask1] + lod[mask1]

            mask2 = (abs(diff_arr) > lod) & (diff_arr > 0)
            dod[mask2] = diff_arr[mask2] - lod[mask2]

            mask3 = (np.isnan(b)) | (np.isnan(e)) | (np.isnan(a)) | (np.isnan(d))
            dod[mask3] = -999

            return dod

        def get_weight_dod(lod):

            """=IF(OC < 95%LoD, OC * (OC / 95%LoD) * 0.5, OC - 95%LoD + 95%LoD * 0.5)"""
            dod = np.zeros(diff_arr.shape)

            warnings.filterwarnings('ignore')

            # weight elevation loss
            mask1 = (abs(diff_arr) < (lod * 1.96)) & (diff_arr < 0)
            dod[mask1] = ((diff_arr[mask1] * (diff_arr[mask1] / (lod[mask1]*1.96))) * 0.5) * -1

            mask1b = (abs(diff_arr) > (lod * 1.96)) & (diff_arr < 0)
            dod[mask1b] = diff_arr[mask1b] + (lod[mask1b] * 1.96) - ((lod[mask1b] * 1.96) * 0.5)

            # weight elevation gain

            mask2 = (abs(diff_arr) < (lod * 1.96)) & (diff_arr > 0)
            dod[mask2] = ((diff_arr[mask2] * (diff_arr[mask2] / (lod[mask2] * 1.96))) * 0.5)

            mask2b = (abs(diff_arr) > (lod * 1.96)) & (diff_arr > 0)
            dod[mask2b] = diff_arr[mask2b] - (lod[mask2b] * 1.96) + ((lod[mask2b] * 1.96) * 0.5)

            mask3 = (np.isnan(b)) | (np.isnan(e)) | (np.isnan(a)) | (np.isnan(d))
            dod[mask3] = -999

            return dod

        # prec_dod = get_dod(lod=prec_lod) # NOT USED FOR NOW.

        if self.lod_method == "threshold":
            rob_dod = get_dod(lod=rob_lod)
        elif self.lod_method == "weighted":
            rob_dod = get_weight_dod(lod=rob_lod)
        else:
            sys.exit("Error: The requested LoD method is not supported use either 'threshold' or 'weighted'.")

        with rasterio.open(self.ras_out_path, "w", **self.out_meta_data) as dest:
            dest.write(rob_dod.astype('float32'), 1)
            dest.write(rob_lod.astype('float32'), 2)
            dest.write(diff_arr.astype('float32'), 3)
            # dest.write(diff_arr.astype('float32'), 3)

        if self.mask is not None:
            mask_it(raster=self.ras_out_path, shp_path=self.mask, epsg=self.epsg.data)


    def close_rasterios(self):
        for ras in self.rasters:
            ras.close()

    def remove_temps(self):
        print('delete the temp raster files.')
        for i in self.temp_log:
            try:
                os.remove(i)
            except OSError as e:
                print(e)
