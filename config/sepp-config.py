import sys
from glob import glob
import numpy as np
from sourcextractor.config import *

#### READ ARGUMENTS PASSED THROUGH --python-arg #########
def str2dict(str_dict):
    keys = []
    for e in str_dict.split(":")[:-1]:
        key = e.split(",")[-1]
        key = key.replace("{", "")
        key = key.replace(" ","")
        keys.append(key)
    values = []
    for e in str_dict.split(":")[1:]:
        val = []
        el = e.split(",")
        el = el if el[-1][-1]=="}" else el[:-1]
        for l in el:
            l = l.replace(" ", "")
            l = l.replace("[", "")
            l = l.replace("]", "")
            l = l.replace('}', "")
            val.append(l)
        if len(val)==1: val = val[0]
        values.append(val)
    dic = dict(zip(keys, values))
    return dic
args = str2dict(sys.argv[1])

##### THESE NEXT LINES DO SOME MORE CONFIGURATION #######
fit_case = args['fit_case']

set_engine('levmar')
set_max_iterations(500)
use_iterative_fitting(True)
set_meta_iterations(3)
set_deblend_factor(1.0) # can be 0.95
set_meta_iteration_stop(0.02)  ## increase -> faster!

###################################################################################
################################ LOAD IMAGES ######################################

list_of_IMG_names = args['list_of_IMG_names']
list_of_WHT_names = args['list_of_WHT_names']
list_of_PSF_names = args['list_of_PSF_names']

mag_zeropoint = {'F090W': 28.90,
                 'F115W': 28.90,
                 'F150W': 28.90,
                 'F182M': 28.90,
                 'F200W': 28.90,
                 'F210M': 28.90,
                 'F250M': 28.90,
                 'F277W': 28.90,
                 'F300M': 28.90,
                 'F335M': 28.90,
                 'F356W': 28.90,
                 'F410M': 28.90,
                 'F430M': 28.90,
                 'F444W': 28.90,
                 'F460M': 28.90,
                 'F480M': 28.90,}

list_of_IMG_names = list( map( lambda x: x, list_of_IMG_names) )
list_of_WHT_names = list( map( lambda x: x, list_of_WHT_names) )
list_of_PSF_names = list( map( lambda x: x, list_of_PSF_names) )

# print to verify how they are loaded
imgroup = load_fits_images(
            images      = list_of_IMG_names,
            psfs        = list_of_PSF_names,
            weights     = list_of_WHT_names,
            weight_type = 'weight',
            weight_threshold=1.e-6)


imgroup.split(ByKeyword('FILTER'))
mesgroup = MeasurementGroup(imgroup)
###################################################################################
###################################################################################



###################################################################################
########################### RUN APERTURE PHOTOMETRY ###############################
# all_apertures = []
# pix_diameter = 25 # pixels

# # loop over every band in the measurement image group and measure aperture photometry in each
# for band,img in mesgroup:
#     all_apertures.extend(add_aperture_photometry(img, pix_diameter) )
# add_output_column('APER', all_apertures)
###################################################################################
###################################################################################





###################################################################################
################################ DEFINE MODELS ####################################

### Sersic profile (detection mode)
if fit_case == "sersic_rg4" : 
    
    x,y = get_pos_parameters()
    
    rad = FreeParameter(lambda o: o.radius, Range(lambda v, o: (.0001, 1.5*v), RangeType.EXPONENTIAL))
    
    lrd=DependentParameter( lambda re: 1.015**(re - 10), rad )
    add_prior( lrd, 0.027/0.03,  0.5) 
    
    sersic = FreeParameter( 2.0, Range((0.3, 8.4), RangeType.LINEAR))
    X_sersic = DependentParameter( lambda n: np.log( (n-0.25)/(10-n) ), sersic )
    add_prior( X_sersic, -2.5, 1.5 )

    e1 = FreeParameter( 0.0, Range((-0.9999, 0.9999), RangeType.LINEAR))
    e2 = FreeParameter( 0.0, Range((-0.9999, 0.9999), RangeType.LINEAR))
    emod = DependentParameter( lambda x,y: np.sqrt( x*x + y*y ), e1, e2 )
    angle = DependentParameter( lambda e1,e2 : 0.5*np.arctan2( e1, e2 ), e1, e2 )
    ratio = DependentParameter( lambda e : np.abs(1-e)/(1+e), emod )
    add_prior( e1, 0.0, 0.25 )
    add_prior( e2, 0.0, 0.25 )

    ra, dec, wc_rad, wc_angle, wc_ratio = get_world_parameters(x, y, rad, angle, ratio)
    
    add_output_column('X_MODEL', x)
    add_output_column('Y_MODEL', y)
    add_output_column('RA_MODEL', ra)
    add_output_column('DEC_MODEL', dec)
    add_output_column('RADIUS', wc_rad)
    add_output_column('AXRATIO', wc_ratio)
    add_output_column('ANGLE', wc_angle)
    add_output_column('E1',e1)
    add_output_column('E2',e2)
    add_output_column('SERSIC', sersic)
    add_output_column('X_SERSIC', X_sersic)
    
    add_output_column('DET-IMG_RADIUS', rad)
    add_output_column('DET-IMG_AXRATIO', ratio)
    add_output_column('DET-IMG_ANGLE', angle)

    i = 0
    flux = {}
    mag = {}
    dx = {}
    xx={}
    dy = {}
    yy={}

    for band,group in mesgroup: 
        print(band)
        
        flux[i] = get_flux_parameter()
        mag[i] = DependentParameter(lambda f, zp=mag_zeropoint[band]: -2.5 * np.log10(f) + zp, flux[i] )
        
        # the centroid is fixed for all bands
        add_model(group, 
                  SersicModel(x, y, flux[i], rad, ratio, angle, sersic ) )

        add_output_column(f'MAG_MODEL_{band}', mag[i])
        add_output_column(f'FLUX_MODEL_{band}', flux[i])
        i+=1

### Sersic profile (association mode)
if fit_case == "sersic_full_assoc" :
    # 1  : x           -> o.centroid_x
    # 2  : y           -> o.centroid_y
    # 3  : group_id    -> o.assoc_value_2
    # 4  : flux_mean   -> o.assoc_value_3
    # 5  : mag_mean    -> o.assoc_value_4
    # 6  : a_image     -> o.assoc_value_5
    # 7  : b_image     -> o.assoc_value_6
    # 8  : theta_image -> o.assoc_value_7
    # 9  : ax_ratio    -> o.assoc_value_8
    # 10 : bigsize     -> o.assoc_value_9

    coord_param_range = Range(lambda v, o: (v - 1*o.assoc_value_5, v + 1*o.assoc_value_5), RangeType.LINEAR)
    x = FreeParameter(lambda o: o.centroid_x, coord_param_range) 
    y = FreeParameter(lambda o: o.centroid_y, coord_param_range) 
    
    # rad = FreeParameter(lambda o: 1.3*o.assoc_value_5, Range(lambda v, o: (v*0.01, 5*v), RangeType.EXPONENTIAL))
    rad = FreeParameter(lambda o: 1.3*o.assoc_value_5, Range(lambda v, o: (v*0.01, 100*v), RangeType.EXPONENTIAL))
    
    lrd=DependentParameter( lambda re: 1.015**(re - 10), rad )
    add_prior( lrd, 0.027/0.03,  0.5) 

    if True:
        sersic = FreeParameter( 2.0, Range((0.3, 8.4), RangeType.LINEAR))
        X_sersic = DependentParameter( lambda n: np.log( (n-0.25)/(10-n) ), sersic )
        add_prior( X_sersic, -2.5, 1.5 )
    if False:
        sersic = FreeParameter( 2.0, Range((0.3, 5.0), RangeType.LINEAR))
        X_sersic = DependentParameter( lambda n: np.log( (n-0.25)/(6-n) ), sersic )
        add_prior( X_sersic, -2.5, 1.5 )

    e1 = FreeParameter( 0.0, Range((-0.9999, 0.9999), RangeType.LINEAR))
    e2 = FreeParameter( 0.0, Range((-0.9999, 0.9999), RangeType.LINEAR))
    emod = DependentParameter( lambda x,y: np.sqrt( x*x + y*y ), e1, e2 )
    angle = DependentParameter( lambda e1,e2 : 0.5*np.arctan2( e1, e2 ), e1, e2 )
    ratio = DependentParameter( lambda e : np.abs(1-e)/(1+e), emod )
    add_prior( e1, 0.0, 0.25 )
    add_prior( e2, 0.0, 0.25 )

    ra, dec, wc_rad, wc_angle, wc_ratio = get_world_parameters(x, y, rad, angle, ratio)
    
    add_output_column('X_MODEL', x)
    add_output_column('Y_MODEL', y)
    add_output_column('RA_MODEL', ra)
    add_output_column('DEC_MODEL', dec)
    add_output_column('RADIUS', wc_rad)
    add_output_column('AXRATIO', wc_ratio)
    add_output_column('ANGLE', wc_angle)
    add_output_column('E1',e1)
    add_output_column('E2',e2)
    add_output_column('SERSIC', sersic)
    add_output_column('X_SERSIC', X_sersic)
    
    add_output_column('DET-IMG_RADIUS', rad)
    add_output_column('DET-IMG_AXRATIO', ratio)
    add_output_column('DET-IMG_ANGLE', angle)

    i = 0
    flux = {}
    mag = {}
    dx = {}
    xx={}
    dy = {}
    yy={}

    for band,group in mesgroup: 
        print(band)
        
        flux[i] = FreeParameter(lambda o: o.assoc_value_3)
        # flux[i] = FreeParameter(lambda o, zp=mag_zeropoint[band]: 10**(0.4*(zp - o.assoc_value_4)))
        mag[i] = DependentParameter(lambda f, zp=mag_zeropoint[band]: -2.5 * np.log10(f) + zp, flux[i] )
        
        # the centroid is fixed for all bands
        add_model(group, 
                  SersicModel(x, y, flux[i], rad, ratio, angle, sersic ) )

        add_output_column(f'MAG_MODEL_{band}', mag[i])
        add_output_column(f'FLUX_MODEL_{band}', flux[i])
        i+=1

# we can print some info about the models        
print_model_fitting_info(mesgroup, show_params=True, prefix='')