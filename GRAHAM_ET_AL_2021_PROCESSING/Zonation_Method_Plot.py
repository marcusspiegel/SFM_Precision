import os
import geopandas as gpd
from matplotlib import pyplot as plt
from matplotlib import rc
from matplotlib.colors import LinearSegmentedColormap
from matplotlib import colors
import pandas as pd

def set_style():
    plt.style.use('bmh')
    font = {'family': 'Tahoma',
            'weight': 'ultralight',
            'size': 10}
    rc('font', **font)


def create_plot(BeaverZones_out, site_grid, feed_signs, figure_save):
    print('Generating zonation method plot...')

    BeaverZones_out = gpd.read_file(BeaverZones_out)
    BeaverZones_out['Name'] = ['Foraging Observed' if x == 1 else 'No Foraging' for
                                      x in BeaverZones_out['signs_YN']]
    BeaverZones_out = BeaverZones_out[['geometry', 'Name']]
    site_grid = gpd.read_file(site_grid)
    site_grid['Name'] = '20m Grid'
    feed_signs = gpd.read_file(feed_signs)
    feed_signs['Name'] = 'Feeding signs'
    feed_signs= feed_signs[['geometry', 'Name']]

    feed_buff = gpd.GeoDataFrame(geometry=feed_signs.buffer(10))
    feed_buff['Name'] = 'Feeding buffer'
    feed_buff = feed_buff.dissolve(by='Name', as_index=False)

    merge_gdf = pd.concat([site_grid, BeaverZones_out, feed_signs, feed_buff])

    # set matplotlib style...
    set_style()

    # build plot
    beaver_z_cmap = colors.ListedColormap(['white','white', '#e7298a', '#d95f02', '#1b9e77'])

    ax = merge_gdf.plot( cmap=beaver_z_cmap, column='Name', legend=True,
                        legend_kwds={'facecolor': 'white', 'ncol': 2},
                        edgecolor='black', markersize=20, alpha=0.6,figsize=(5, 9))
    ax.set_facecolor('white')
    ax.grid(False)
    leg = ax.get_legend()
    leg.set_bbox_to_anchor((0.6, -0.03, 0.6, 0.))
    plt.tight_layout(rect=[0.02, 0.02, 0.98, 0.98])

    plt.savefig(fname=figure_save, dpi=300, format='jpg')
    plt.show()


if __name__ == '__main__':
    create_plot(BeaverZones_out=os.path.abspath('C:/HG_Projects/CWC_Drone_work/CHM/Beaver_Zones20m.gpkg'),
                site_grid=os.path.abspath('C:/HG_Projects/CWC_Drone_work/ZoneMethodPlot_data/'
                                          'grid_20m.gpkg'),
                feed_signs=os.path.abspath('C:/HG_Projects/CWC_Drone_work/shp_files/Feed_signs_All.gpkg'),
                figure_save=os.path.abspath('C:/HG_Projects/CWC_Drone_work/maps/Zone_method.png')
                )
