import matplotlib as mpl
import matplotlib.pyplot as plt
import pandas as pd
import numpy as np

from matplotlib.collections import LineCollection

mpl.rcParams['font.family'] = 'monospace'
mpl.rcParams['font.sans-serif'] = 'FreeMono'
mpl.rcParams['font.size'] = 12

################
# PANDAS NOTES #
################
# we can index our data now something like:
#   data['string'].loc[keys[1]].iloc[-1]
#        |                |         |
#        --- column name  |         |
#                         -- key    --- row index (indexing starts at 0, -1 means end, -2 means one before end, etc.)
# NO KEY FOR THIS DATA SET

############################
# QUICK ON / OFFS & PARAMS #
############################

percent_on = 86.32 / 100.0 # %/100

### NIST INPUT ###
dir="./csv/"

name_h2a = dir+"h2a.csv"
name_h2b = dir+"h2b.csv"
name_h3a = dir+"h3a.csv"
name_h3b = dir+"h3b.csv"
name_h4a = dir+"h4a.csv"
name_h4b = dir+"h4b.csv"
name_rpm = dir+"rpm.csv"
name_cond = dir+"cond.csv"
name_evap = dir+"evap.csv"


temp_name = "T"
pres_name = "P"
dens_name = "D"
enth_name = "H"
entr_name = "S"
rpm_name  = "RPM"

##################
# USER FUNCTIONS #
##################

def _to_cm3s_(_gpmin_):
  return _gpmin_*63.0902

def _to_gpm_(_cm3sin_):
  return _cm3sin_/63.0902

def _to_mpag_(_pin_):
  return _pin_*0.00689476

def _to_psig_(_pin_):
  return _pin_/0.00689476

def _to_lbhr_(_gsin_):
  return _gsin_*7.93664

def _to_kelvin_(_fin_):
  return (_fin_-32.0)/1.8+273.15 #Kelvin = ((Fahrenheit - 32) / 1.8) + 273.15

def _to_f_(_kin_):
  return _kin_*9.0/5.0-459.67

def __get_year_time_h_lv__(yy_in,mo_in,dd_in,h_in,m_in):
  if ((int(yy_in) % 4) == 0):
    month_days = np.array([31,29,31,30,31,30,31,31,30,31,30,31])
  else:
    month_days = np.array([31,28,31,30,31,30,31,31,30,31,30,31])
  month_hours = 0
  for ii in range(int(mo_in)-1):
    month_hours = month_hours + month_days[ii]*24
  time_out = float(month_hours + (int(dd_in)-1)*24 + int(h_in) + int(m_in)/60)
  return time_out

def _to_btuhr_(_ein_):
  return _ein_ / 1000.0 * 3412.14 # W to Btu/hr

Ru = 83144626.1815324
mw_air = 28.96518 # g/mol
Rg = Ru/mw_air
def _cp_air_(_tin_):
  return (28.11+0.001967*_tin_+0.000004802*_tin_**2-0.000000001966*_tin_**3)/mw_air # J/g-K
def _dens_air_(_tin_):
  return 1013250.0 / Rg / _tin_ # g/cm^3
def _to_cfm_(_vin_):
  return _vin_/471.947

#####################################
# READ DATA IN & SETUP FOR ANALYSIS #
#####################################
h2a  = pd.read_csv(name_h2a)
h2b  = pd.read_csv(name_h2b)
h3a  = pd.read_csv(name_h3a)
h3b  = pd.read_csv(name_h3b)
h4a  = pd.read_csv(name_h4a)
h4b  = pd.read_csv(name_h4b)

sat_cond  = pd.read_csv(name_cond)
sat_evap  = pd.read_csv(name_evap)

rpm = pd.read_csv(name_rpm)
hz  = rpm['RPM']/60.0

sh = (h2a[temp_name] - sat_evap[temp_name])*1.8
sc = (sat_cond[temp_name] - h4b[temp_name])*1.8

print(np.average(sh),np.average(sc))

disp = 2.82 # in^3
disp_ft3 = disp / 12.0**3
disp = disp * 2.54**3 # cm^3

dens_rated = 0.50031 # lbm/ft^3
m_dot_rated = 211 # lbm / hr
hz_rated = 75 # rev/sec
rph = hz_rated*60*60

m_dot_th = dens_rated * rph * disp_ft3

eta_vol = m_dot_rated / m_dot_th

m_dot = h2b[dens_name] * eta_vol * disp * hz

qc = m_dot * (h2b[enth_name] - h4b[enth_name]) # g/s * J/g = J/s = W instantaneous
qc_avg_on = np.average(qc) # Average watts during on time
qc_avg    = qc_avg_on * percent_on # average watts during 24 hr test

btu_cooling_capacity = _to_btuhr_(qc_avg)

plt.figure(1,figsize=(10,8))
one,=plt.plot(sh)
two,=plt.plot(sc)
plt.legend([one,two],['SH','SC'])
plt.title("Superheat & Subcooling")
plt.ylabel("T [F]")
plt.grid(True,linestyle="--")


plt.figure(2,figsize=(10,8))
one,=plt.plot(m_dot)
two,=plt.plot(qc/1000.0)
plt.legend([one,two],['$m_{dot}$','$q_c$'])
plt.title("Mass Flow & Cooling Capacity")
plt.ylabel("[g/s] & [kW]")
plt.grid(True,linestyle="--")
plt.show()

print("--------------------------------------------------------------")
print("Ref enthalpy states:")
print("  h2a :: %.2f [J/g]"%( np.average(h2a[enth_name]) ))
print("  h2b :: %.2f [J/g]"%( np.average(h2b[enth_name]) ))
print("  h3a :: %.2f [J/g]"%( np.average(h3a[enth_name]) ))
print("  h3b :: %.2f [J/g]"%( np.average(h3b[enth_name]) ))
print("  h4a :: %.2f [J/g]"%( np.average(h4a[enth_name]) ))
print("  h4b :: %.2f [J/g]"%( np.average(h4b[enth_name]) ))
print("--------------------------------------------------------------")
print("Cooling capacity :: %.2f [Btu/hr]"%( btu_cooling_capacity ))
print("--------------------------------------------------------------")

exit()