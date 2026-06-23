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

csv_out = True
plt_out = True

start_time = "04/13/2025 6:02"
end_time   = "04/14/2025 6:01"
door_case= "Program Validation"

sys_pres_threshold = 85 # psig, system on if p >= threshold

request_var1 = "Liquid Pressure "
request_var2 = "Suction Presure "
request_var_units = r"[psig]"

filename = "ID6SU12WE DOE 2.csv"

p_liq_name = "Liquid Pressure "
p_suc_name = "Suction Presure "

name_2a = list()
name_2a.append("Right TXV Bulb ")
name_2a.append("CTR TXV Bulb")
name_2a.append("Left TXV Bulb")

name_2b = "Suction line into Comp"
name_3a = "Discharge line from comp"
name_3b = "Ref Temp in HeatX"
name_4a = "Ref Temp out HeatX"
name_4b = list()
name_4b.append("Left TXV Inlet")
name_4b.append("CTR TXV Inlet")
name_4b.append("Right TXV Inlet ")

name_wi  = "Water in HeatX"
name_wo = "Water out HeatX"

name_ai = list()
name_ai.append("Air in left evap 6 in LE")
name_ai.append("Air in left evap 6 in RE")
name_ai.append("Air in ctr evap 6 in LE")
name_ai.append("Air in ctr evap 6 in RE")
name_ai.append("Air in right evap 6 in LE")
name_ai.append("Air in right evap 6 in RE")

name_ao = list()
name_ao.append("Air off left evap 6 in LE")
name_ao.append("Air off left evap 6 in RE")
name_ao.append("Air off ctr evap 6 in LE")
name_ao.append("Air off ctr evap 6 in RE")
name_ao.append("Air off right evap 6 in LE")
name_ao.append("Air off right evap 6 in RE")



ph_diag =r"""
(P)      PH Diagram
/|\           .
 |   4____._____.______ 3
 |    |.         .    /
 |   .|           .  /
 |  . |____________./
 | .  1             .2
 |.                  .
 |------------------------> (h)
"""
piping_diag =r"""
              ______
          4a |      | 3b
   ------<---| COND |----<----
   |         |______|        | 3a
   | 4b                     _|__
  \|/                      /    \ 
  /|\                     / COMP \ 
   |          ______     /________\ 
   |         |      |        | 2b
   ------>---| EVAP |---->----
      1      |______| 2a
""" 

##################
# USER FUNCTIONS #
##################

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

#####################################
# READ DATA IN & SETUP FOR ANALYSIS #
#####################################

## CHECK 
water_pres = _to_mpag_(15)

request_time1 = start_time
request_time2 = end_time

strings = request_time1.split(" ")
dates = strings[0].split("/") # [month, day, year]
times = strings[1].split(":") # [hour, minute]
request_time_h1 = __get_year_time_h_lv__(dates[2],dates[0],dates[1],times[0],times[1])

strings = request_time2.split(" ")
dates = strings[0].split("/") # [month, day, year]
times = strings[1].split(":") # [hour, minute]
request_time_h2 = __get_year_time_h_lv__(dates[2],dates[0],dates[1],times[0],times[1])

data = pd.read_csv(filename)

try:
  lv_date = data['Date'].tolist()
  lv_time = data['Time'].tolist()
except:
  lv_timestamp = data['Timestamp'].tolist()
  lv_date = list(); lv_time = list();
  for kk in range(len(lv_timestamp)):
    strings = lv_timestamp[kk].split(" ")
    lv_date.append(strings[0])
    lv_time.append(strings[1])

strings1 = lv_date[0]
strings2 = lv_time[0]

dates = strings1.split("/") # [month, day, year]
times = strings2.split(":") # [hour, minute]

time_start = __get_year_time_h_lv__(dates[2],dates[0],dates[1],times[0],times[1])

yth = []
tth = []

for kk in range(len(lv_time)):
  strings1 = lv_date[kk]
  strings2 = lv_time[kk]
  #strings = lv_time[kk].split(" ")
  #strings1=strings[0]
  #strings2=strings[1]
  dates = strings1.split("/")
  times = strings2.split(":")
  yth.append(__get_year_time_h_lv__(dates[2],dates[0],dates[1],times[0],times[1]))
  tth.append( ( float(yth[kk]) - time_start ) )

data['yth'] = yth # year time in hours
data['tth'] = tth # test time in hours

temp_array1 = np.array(abs(np.asarray(data['yth']) - request_time_h1))
temp_array2 = np.array(abs(np.asarray(data['yth']) - request_time_h2))
request_index1 = np.argmin(temp_array1)
request_index2 = np.argmin(temp_array2)

start_index = request_index1
end_index   = request_index2

p_liq = list()
p_suc = list()

t_2a = list()
t_2b = list()

t_3a = list()
t_3b = list()

t_4a = list()
t_4b = list()

t_ai = list()
t_ao = list()

t_wi = list()
t_wo = list()

rpm = list()

time_total = len(yth)
count = 0
for kk in range(time_total):
  if (data[p_liq_name].iloc[kk] >= sys_pres_threshold):
    count = count + 1
    p_liq.append(_to_mpag_(data[p_liq_name].iloc[kk]))
    p_suc.append(_to_mpag_(data[p_suc_name].iloc[kk]))
    t_2a_arr = list()
    for jj in range(len(name_2a)):
      t_2a_arr.append(data[name_2a[jj]].iloc[kk])
    t_2a_avg = np.average(np.asarray(t_2a_arr))
    t_2a.append(_to_kelvin_(t_2a_avg))
    t_2b.append(_to_kelvin_(data[name_2b].iloc[kk]))
    t_3a.append(_to_kelvin_(data[name_3a].iloc[kk]))
    t_3b.append(_to_kelvin_(data[name_3b].iloc[kk]))
    t_4a.append(_to_kelvin_(data[name_4a].iloc[kk]))
    t_4b_arr = list()
    for jj in range(len(name_4b)):
      t_4b_arr.append(data[name_4b[jj]].iloc[kk])
    t_4b_avg = np.average(np.asarray(t_4b_arr))
    t_4b.append(_to_kelvin_(t_4b_avg))
    t_ai_arr = list()
    for jj in range(len(name_ai)):
      t_ai_arr.append(data[name_ai[jj]].iloc[kk])
    t_ai_avg = np.average(np.asarray(t_ai_arr))
    t_ai.append(_to_kelvin_(t_ai_avg))
    t_ao_arr = list()
    for jj in range(len(name_ao)):
      t_ao_arr.append(data[name_ao[jj]].iloc[kk])
    t_ao_avg = np.average(np.asarray(t_ao_arr))
    t_ao.append(_to_kelvin_(t_ao_avg))
    t_wi.append(_to_kelvin_(data[name_wi].iloc[kk]))
    t_wo.append(_to_kelvin_(data[name_wo].iloc[kk]))
    rpm.append(data["Compressor RPM"].iloc[kk])


df_h2a  = pd.DataFrame({'T' : t_2a, 'P' : p_suc})
df_h2b  = pd.DataFrame({'T' : t_2b, 'P' : p_suc})

df_h3a  = pd.DataFrame({'T' : t_3a, 'P' : p_liq})
df_h3b  = pd.DataFrame({'T' : t_3b, 'P' : p_liq})

df_h4a  = pd.DataFrame({'T' : t_4a, 'P' : p_liq})
df_h4b  = pd.DataFrame({'T' : t_4b, 'P' : p_liq})

df_psat_cond = pd.DataFrame({'P' : p_liq})
df_psat_evap = pd.DataFrame({'P' : p_suc})

df_rpm  = pd.DataFrame({'RPM' : rpm})

if (csv_out == True):
  df_h2a.to_csv('h2a.csv',index=False)
  df_h2b.to_csv('h2b.csv',index=False)
  df_h3a.to_csv('h3a.csv',index=False)
  df_h3b.to_csv('h3b.csv',index=False)
  df_h4a.to_csv('h4a.csv',index=False)
  df_h4b.to_csv('h4b.csv',index=False)
  #df_wi.to_csv('hci.csv',index=False)
  #df_wo.to_csv('hco.csv',index=False)
  df_rpm.to_csv('rpm.csv',index=False)
  df_psat_cond.to_csv('cond.csv',index=False)
  df_psat_evap.to_csv('evap.csv',index=False)

percent_on = count/time_total

p_liq_avg = np.average(np.asarray(p_liq))
p_suc_avg = np.average(np.asarray(p_suc))

T2a_avg = np.average(np.asarray(t_2a))
T2b_avg = np.average(np.asarray(t_2b))

T3a_avg = np.average(np.asarray(t_3a))
T3b_avg = np.average(np.asarray(t_3b))

T4a_avg = np.average(np.asarray(t_4a))
T4b_avg = np.average(np.asarray(t_4b))

Tai_avg_run = np.average(np.asarray(t_ai))
Tao_avg_run = np.average(np.asarray(t_ao))

Twi_avg = np.average(np.asarray(t_wi))
Two_avg = np.average(np.asarray(t_wo))

temp_array = list()
for kk in range(len(name_ai)):
  temp_array.append(np.average(np.asarray( _to_kelvin_(data[name_ai[kk]]) )))
Tai_avg = np.average(np.asarray( temp_array ))

temp_array = list()
for kk in range(len(name_ao)):
  temp_array.append(np.average(np.asarray( _to_kelvin_(data[name_ao[kk]]) )))
Tao_avg = np.average(np.asarray( temp_array ))


# add water temps in and out during run time
# add air temps average during on time

print("  System Information")
print("----------------------------------------")
print("On time :: %.2f [%%]"%(percent_on*100))
print("  On time averages :: ")
print("    Liquid  Pressure : %.2f [psig]"%(_to_psig_(p_liq_avg)))
print("    Suction Pressure : %.2f [psig]"%(_to_psig_(p_suc_avg)))
print("    T2a              : %.2f [F]"%(_to_f_(T2a_avg)))
print("    T2b              : %.2f [F]"%(_to_f_(T2b_avg)))
print("    T3a              : %.2f [F]"%(_to_f_(T3a_avg)))
print("    T3b              : %.2f [F]"%(_to_f_(T3b_avg)))
print("    T4a              : %.2f [F]"%(_to_f_(T4a_avg)))
print("    T4b              : %.2f [F]"%(_to_f_(T4b_avg)))
print("    T_water_in       : %.2f [F]"%(_to_f_(Twi_avg)))
print("    T_water_out      : %.2f [F]"%(_to_f_(Two_avg)))
print("    T_air_in         : %.2f [F]"%(_to_f_(Tai_avg_run)))
print("    T_air_out        : %.2f [F]"%(_to_f_(Tao_avg_run)))
print("----------------------------------------")
print("Avg air inlet  evap  : %.2f [F]"%(_to_f_(Tai_avg)))
print("Avg air outlet evap  : %.2f [F]"%(_to_f_(Tao_avg)))

print(ph_diag)
print(piping_diag)


#########
# PLOTS #
#########
if (plt_out == True):
  fig_aspect = (12,6)
  _time_    = data['tth'].iloc[start_index:end_index]
  plot_var1 = data[request_var1].iloc[start_index:end_index]
  plot_var2 = data[request_var2].iloc[start_index:end_index]
  plot_title = door_case+" "+start_time+" - "+end_time
  plt.figure(3,figsize=fig_aspect)
  plt.title(plot_title)
  one ,= plt.plot(_time_,plot_var1)
  two ,= plt.plot(_time_,plot_var2)
  plt.xlabel("test time [hr]")
  plt.ylabel("%s"%request_var_units)
  plt.legend([one,two],["%s"%request_var1,"%s"%request_var2])
  plt.grid(True, linestyle='--')
  plt.show()

exit()

