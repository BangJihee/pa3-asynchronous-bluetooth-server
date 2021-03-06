from btserver import BTServer
from bterror import BTError
from neo import Gpio
import argparse
import asyncore
import json
from threading import Thread
from time import sleep, time
from datetime import datetime
from json import dumps
import logging

# ------------ Alpha sense data sheet -------------
NO2_WE = 220;
NO2_AE = 260;
NO2_alpha = 0.207;
O3_WE = 414;
O3_AE = 400;
O3_alpha = 0.256;
CO_WE = 346;
CO_AE = 274;
CO_alpha = 0.276;
SO2_WE = 300;
SO2_AE = 294;
SO2_alpha = 0.300;


# ------------------------------------------------

def contol_mux(a, b, c, d):  # use binary bit to control mux
    neo.digitalWrite(gpiopins[0], d)
    neo.digitalWrite(gpiopins[1], c)
    neo.digitalWrite(gpiopins[2], b)
    neo.digitalWrite(gpiopins[3], a)
    raw = int(open("/sys/bus/iio/devices/iio:device0/in_voltage0_raw").read())
    scale = float(open("/sys/bus/iio/devices/iio:device0/in_voltage_scale").read())
    return raw, scale


# ---------------------------N table -------------------------------------
# array for calculate alph
# temp              -30,  -20   -10     0    10     20   30    40    50
# index               0,    1,    2,    3,    4,    5,    6,    7 ,   8
NO2_tempArray = [1.18, 1.18, 1.18, 1.18, 1.18, 1.18, 1.18, 2.00, 2.70]  # SN1
O3_tempArray = [0.18, 0.18, 0.18, 0.18, 0.18, 0.8, 0.8, 0.8, 2.87]  # SN2
CO_tempArray = [1.40, 1.03, 0.85, 0.62, 0.30, 0.03, -0.25, -0.48, -0.80]  # SN3
SO2_tempArray = [0.85, 0.85, 0.85, 0.85, 0.85, 1.15, 1.45, 1.75, 1.95]  # SN4


# ------------------------------------------------------------------------

def get_n(temper, air):
    i = 0  # index
    mulx = 0  # multiple #times
    if (-30 <= temper < -20):
        i = 0;
        mulx = temper + 30
    elif (-20 <= temper < -10):
        i = 1;
        mulx = temper + 20
    elif (-10 <= temper < 0):
        i = 2;
        mulx = temper + 10
    elif (0 <= temper < 10):
        i = 3;
        mulx = temper
    elif (10 <= temper < 20):
        i = 4;
        mulx = temper - 10
    elif (20 <= temper < 30):
        i = 5;
        mulx = temper - 20
    elif (30 <= temper < 40):
        i = 6;
        mulx = temper - 30
    elif (40 <= temper < 50):
        i = 7;
        mulx = temper - 40
    elif (50 <= temper):
        i = 8;  # if temperature exceed 50 just give 50'C data

    N = 0.0

    if (air == 'NO2'):
        if (i == 8):
            N = NO2_tempArray[i]
        else:
            tmp = (NO2_tempArray[i + 1] - NO2_tempArray[i]) / 10.0
            N = NO2_tempArray[i] + (tmp * mulx)

    elif (air == 'O3'):
        if (i == 8):
            N = O3_tempArray[i]
        else:
            tmp = (O3_tempArray[i + 1] - O3_tempArray[i]) / 10.0
            N = O3_tempArray[i] + (tmp * mulx)

    elif (air == 'CO'):
        if (i == 8):
            N = CO_tempArray[i]
        else:
            tmp = (CO_tempArray[i + 1] - CO_tempArray[i]) / 10.0
            N = CO_tempArray[i] + (tmp * mulx)

    elif (air == 'SO2'):
        if (i == 8):
            N = SO2_tempArray[i]
        else:
            tmp = (SO2_tempArray[i + 1] - SO2_tempArray[i]) / 10.0
            N = SO2_tempArray[i] + (tmp * mulx)

    return N


# --------------------------- AQI table ----------------------------------------
# AQI              0-50,  51-100, 101-150, 151-200, 201-300, 301-400, 401-500
# index               0,       1,       2,       3,       4,       5,       6,
# MAX (03, PM25, CO, SO2, NO2, AQI)
O3_MaxAqiArray = [55.0, 71.0, 86.0, 106.0, 200.0, 0.0, 0.0]
PM25_MaxAqiArray = [12.1, 35.5, 55.5, 150.5, 250.5, 350.5, 500.4]
CO_MaxAqiArray = [4.5, 9.5, 12.5, 15.5, 30.5, 40.5, 50.4]
SO2_MaxAqiArray = [36.0, 76.0, 186.0, 305.0, 605.0, 805.0, 1004.0]
NO2_MaxAqiArray = [54.0, 101.0, 361.0, 650.0, 1250.0, 1650.0, 2049.0]
Aqi_MaxAqiArray = [51.0, 101.0, 151.0, 201.0, 301.0, 401.0, 500.0]

# MIN (03, PM25, CO, SO2, NO2, AQI)
O3_MinAqiArray = [0.0, 55.0, 71.0, 86.0, 106.0, 0.0, 0.0]
PM25_MinAqiArray = [0.0, 12.1, 35.5, 55.5, 150.5, 250.5, 350.5]
CO_MinAqiArray = [0.0, 4.5, 9.5, 12.5, 15.5, 30.5, 40.5]
SO2_MinAqiArray = [0.0, 36.0, 76.0, 186.0, 305.0, 605.0, 805.0]
NO2_MinAqiArray = [0.0, 54.0, 101.0, 361.0, 650.0, 1250.0, 1650.0]
Aqi_MinAqiArray = [0.0, 51.0, 101.0, 151.0, 201.0, 301.0, 401.0]


# -------------------------------------------------------------------------------


def AQI_convert(c, air):
    c_low = 0.0
    c_high = 0.0
    i_low = 0.0
    i_high = 0.0
    AQI = 0.0

    if (air == 'PM25'):
        for i in range(0, 7):
            if (PM25_MaxAqiArray[6] < c):
                AQI = 500
                break;

            elif (PM25_MinAqiArray[i] <= c < PM25_MaxAqiArray[i]):
                c_low = PM25_MinAqiArray[i];
                c_high = PM25_MaxAqiArray[i];
                i_low = Aqi_MinAqiArray[i];
                i_high = Aqi_MaxAqiArray[i];
                break;

    elif (air == 'CO'):
        for i in range(0, 7):
            if (CO_MaxAqiArray[6] < c):
                AQI = 500
                break;

            elif (CO_MinAqiArray[i] <= c < CO_MaxAqiArray[i]):
                c_low = CO_MinAqiArray[i];
                c_high = CO_MaxAqiArray[i];
                i_low = Aqi_MinAqiArray[i];
                i_high = Aqi_MaxAqiArray[i];
                break;

    elif (air == 'SO2'):
        for i in range(0, 7):
            if (SO2_MaxAqiArray[6] < c):
                AQI = 500
                break;

            elif (SO2_MinAqiArray[i] <= c < SO2_MaxAqiArray[i]):
                c_low = SO2_MinAqiArray[i];
                c_high = SO2_MaxAqiArray[i];
                i_low = Aqi_MinAqiArray[i];
                i_high = Aqi_MaxAqiArray[i];
                break;
    elif (air == 'NO2'):
        for i in range(0, 7):
            if (NO2_MaxAqiArray[6] < c):
                AQI = 500
                break;

            if (NO2_MinAqiArray[i] <= c < NO2_MaxAqiArray[i]):
                c_low = NO2_MinAqiArray[i];
                c_high = NO2_MaxAqiArray[i];
                i_low = Aqi_MinAqiArray[i];
                i_high = Aqi_MaxAqiArray[i];
                break;

    elif (air == 'O3'):
        for i in range(0, 5):
            if (O3_MaxAqiArray[4] < c):
                AQI = 500
                break;

            if (O3_MinAqiArray[i] <= c < O3_MaxAqiArray[i]):

                c_low = O3_MinAqiArray[i];
                c_high = O3_MaxAqiArray[i];
                i_low = Aqi_MinAqiArray[i];
                i_high = Aqi_MaxAqiArray[i];
                break;
    # AQI equation
    if (AQI != 500):
        AQI = (((i_high - i_low) / (c_high - c_low)) * (c - c_low)) + i_low

    return AQI;


if __name__ == '__main__':
    # Create option parser
    usage = "usage: %prog [options] arg"
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", dest="output_format", default="json", help="set output format: csv, json")

    args = parser.parse_args()

    # Create a BT server
    uuid = "94f39d29-7d6d-437d-973b-fba39e49d4ee"
    service_name = "BTServer"
    server = BTServer(uuid, service_name)

    # Create the server thread and run it
    server_thread = Thread(target=asyncore.loop, name="BT Server Thread")
    server_thread.daemon = True
    server_thread.start()

    # epochtime = datetime.now().strftime('%Y-%m-%d %H:%M:%S') #(int)(time())

    neo = Gpio()

    gpiopins = [8, 9, 10, 11]
    gpio = Gpio()

    pinnum = [0, 0, 0, 0]

    # Set GPIO pins to output
    # try:
    #   for pin in gpiopins:
    #       gpio.pinMode(pin, gpio.OUTPUT)
    # except Exception as e:
    #    logger.error("Error : GPIO pin {} .reason {}".format(pin, e.message))

    # Blink example
    for i in range(4):
        neo.pinMode(gpiopins[i], neo.OUTPUT)

    while True:
        for client_handler in server.active_client_handlers.copy():

            # C0
            raw, scale = contol_mux(0, 0, 0, 0)
            sleep(0.05)
            v = raw * scale
            t = (v - 500) / 10 - 6
            t = (t * 1.8) + 32
            print("Temp: {} F ".format(t))

            # C1= NO2_WE
            raw, scale = contol_mux(0, 0, 1, 0)
            sleep(0.05)
            c2 = raw * scale

            # C2 =NO2_AE
            raw, scale = contol_mux(0, 0, 1, 1)
            sleep(0.05)
            c3 = raw * scale

            # SN1= NO2
            SN1 = ((c2 - NO2_WE) - (get_n(t, 'NO2') * (c3 - NO2_AE))) / NO2_alpha
            SN1 = SN1 if (SN1 >= 0) else -SN1
            print("NO2: {} ".format(SN1))

            # C4= O3_WE
            raw, scale = contol_mux(0, 1, 0, 0)
            sleep(0.05)
            c4 = raw * scale

            # C5= O3_AE
            raw, scale = contol_mux(0, 1, 0, 1)
            sleep(0.05)
            c5 = raw * scale

            # SN2 =O3
            SN2 = ((c4 - O3_WE) - (get_n(t, 'O3') * (c5 - O3_AE))) / O3_alpha
            SN2 = SN2 if (SN2 >= 0) else -SN2
            print("O3: {} ".format(SN2))

            # C6= CO_WE
            raw, scale = contol_mux(0, 1, 1, 0)
            sleep(0.05)
            c6 = raw * scale

            # C7= CO_AE
            raw, scale = contol_mux(0, 1, 1, 1)
            sleep(0.05)
            c7 = raw * scale

            # SN3= CO
            SN3 = ((c6 - CO_WE) - (get_n(t, 'CO') * (c7 - CO_AE))) / CO_alpha
            SN3 = SN3 / 1000
            SN3 = SN3 if (SN3 >= 0) else -SN3
            print("CO: {} ".format(SN3))

            # C8 =SO2_WE
            raw, scale = contol_mux(1, 0, 0, 0)
            sleep(0.05)
            c8 = raw * scale

            # C9= SO2_AE
            raw, scale = contol_mux(1, 0, 0, 1)
            sleep(0.05)
            c9 = raw * scale

            #  SN4= SO2
            SN4 = ((c8 - SO2_WE) - (get_n(t, 'SO2') * (c9 - SO2_AE))) / SO2_alpha
            SN4 = SN4 if (SN4 >= 0) else -SN4
            print("SO2: {} ".format(SN4))

            # C11 =PM2.5
            raw, scale = contol_mux(1, 0, 1, 1)
            sleep(0.05)
            c11 = (raw * scale) / 1000

            # PM2.5
            hppcf = (240.0 * pow(c11, 6) - 2491.3 * pow(c11, 5) + 9448.7 * pow(c11, 4) - 14840.0 * pow(c11,
                                                                                                       3) + 10684.0 * pow(
                c11, 2) + 2211.8 * c11 + 7.9623)
            PM25 = 0.518 + .00274 * hppcf

            print("PM25: {} ".format(PM25))
            print("")
            # print("It's now: {:%Y/%m/%d %H:%M:%S}".format(epochtime))

            AQI_NO2 = AQI_convert(SN1, 'NO2')
            AQI_O3 = AQI_convert(SN2, 'O3')
            AQI_CO = AQI_convert(SN3, 'CO')
            AQI_SO2 = AQI_convert(SN4, 'SO2')
            AQI_PM25 = AQI_convert(PM25, 'PM25')

            print("AQI_NO2:{} ".format(int(AQI_NO2)))
            print("AQI_O3:{}".format(int(AQI_O3)))
            print("AQI_CO:{}".format(int(AQI_CO)))
            print("AQI_SO2 : {}".format(int(AQI_SO2)))
            print("AQI_PM25: {}".format(int(AQI_PM25)))
            print("")

            nowtime = datetime.now()
            print(nowtime)
            print("----------------------------")

            b = "B" #distinct our 4 sensors to use this value

            if args.output_format == "json":
                output = {
                    "MAC": b,
                    "year": nowtime.year,
                    "month": nowtime.month,
                    "day": nowtime.day,
                    "hour": nowtime.hour,
                    "minute": nowtime.minute,
                    "second": nowtime.second,
                    'temp': int(t),  # real temperature
                    'SN1': SN1,  # NO2
                    'SN2': SN2,  # O3
                    'SN3': SN3,  # CO
                    'SN4': SN4,  # SO2
                    'PM25': PM25,
                    'A_SN1': int(AQI_NO2),  # NO2
                    'A_SN2': int(AQI_O3),  # O3
                    'A_SN3': int(AQI_CO),  # CO
                    'A_SN4': int(AQI_SO2),  # SO2
                    'A_PM25': int(AQI_PM25)
                }

                msg = json.dumps(output)
            elif args.output_format == "csv":
                msg = "Time:{}, {}, {}, {}, {}, {}, {}, {} ,{}, {}, {}, {}  ".format(datetime, t, SN1, SN2, SN3, SN4,
                                                                                     AQI_PM25, AQI_NO2, AQI_O3, AQI_CO,
                                                                                     AQI_SO2, AQI_PM25)
            try:
                client_handler.send((msg + '\n').encode('ascii'))
            except Exception as e:
                BTError.print_error(handler=client_handler, error=BTError.ERR_WRITE, error_message=repr(e))
                client_handler.handle_close()

        # Sleep for 5 seconds
        sleep(2.5)
