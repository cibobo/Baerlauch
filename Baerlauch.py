import json
import time

import numpy

from datetime import datetime
from collections import deque

import BinanceRestLib

class TradingChecker(object):
    #TODO: use other time interval instead the fixed 1m
    init_interval = '15m'
    running_interval = '5m'
    interval_factor = 3

    init_limit = 100

    # Static parameters for volumn comparision
    record_factor = 5
    record_number = 3

    # Static parameter for exponential decrease function
    # set 1.2 firstly, so that the record will be reduced to 1/4 after 7.6 min.
    alpha = 1.1

    # Test coins
    symbol_vol = 0
    coin_vol = 0.1

    def __init__(self, symbol):
        # Save the symbol name
        self.symbol = symbol
        
        # Save all average values
        self.average = self.calcuAverageValue(symbol)
        # reduce the volumn average based on 5m
        self.average[5] = self.average[5]/self.interval_factor 

        # save the trading volum based on current credit
        self.trading_vol = self.initTradingVolumn(symbol)

        print(self.average)
        print(self.trading_vol)

        # Create a dict for record volumn
        self.record_vol = deque(maxlen=self.record_number)

        # save the current timestamp to keep 1 min cyclic
        self.last_timestamp = time.time()

    def initTradingVolumn(self, symbol):
        # get the current price with the init trading volumn
        price = BinanceRestLib.getCurrentPriceTicker(symbol[:-3], symbol[-3:])
        # calculate the needed trading volumn
        volumn = {}
        volumn['buy'] = self.coin_vol/price
        volumn['sell'] = self.coin_vol/price
        return volumn

    def calcuAverageValue(self, symbol):
        param = {}
        param['symbol'] = symbol
        param['interval'] = self.init_interval
        param['limit'] = self.init_limit

        result = BinanceRestLib.getService('klines', param)
        print(result)

        # Use numpy to transfer the data to matrix in order to simplify the further work
        R = numpy.array(result).astype(numpy.float)
        # Calculate the average value for the whole data
        # Because each sublist in result is recognized as a column in numpy matrix, therefore calculate the average value with axis 0
        Avg = numpy.mean(R,axis=0)
        
        return Avg

    def checkTradingChance(self):
        param = {}
        param['interval'] = self.running_interval
        param['limit'] = 1
        param['symbol'] = self.symbol

        result = BinanceRestLib.getService('klines', param)[0]
        print(self.symbol, "---------------------------")
        # print(result)

        # update the average values
        # in order to save the memory space, use a weighted moving averag to simulate the simple moving average, 
        # so that the weight of the very beginning data can be ignored after several times of the average update
        factor =0.975
        result_float = numpy.array(result).astype(numpy.float)
        self.average = self.average*factor + result_float*(1-factor) 
        # print(self.average)

        if self.isBuyChance(self.symbol, result_float):
            # get current price
            price = BinanceRestLib.getCurrentPrice(self.symbol[:-3], self.symbol[-3:], self.trading_vol)

            # record the information
            file_out = open('TradingInfo.log','a')
            file_out.write(str(datetime.fromtimestamp(time.time())))
            file_out.write("Find buy change for: " + self.symbol + '\n')
            # save data with "average | current"
            file_out.write("Open Price: " + str(self.average[1]) + " | " + result[1] + '\n')
            file_out.write("Close Price: " + str(self.average[4]) + " | " + result[4] + '\n')
            file_out.write("Trading Volumn: " + str(self.average[5]) + " | " + result[5] + '\n')
            # save current price
            file_out.write("Current price: " + str(price['asks_vol']) + '\n')
            # save volumn record
            file_out.write("Saved Volumn: ")
            for i in range(self.record_number):
                file_out.write("[" + str(self.record_vol[i][0]) + ", " + str(self.record_vol[i][1]) + "], ")
            file_out.write("\n")

            file_out.close()

            print(str(datetime.fromtimestamp(time.time())))
            print("Find buy change for: " + self.symbol + '\n')
            # save data with "average | current"
            print("Open Price: " + str(self.average[1]) + " | " + result[1] + '\n')
            print("Close Price: " + str(self.average[4]) + " | " + result[4] + '\n')
            print("Trading Volumn: " + str(self.average[5]) + " | " + result[5] + '\n')
            # save current price
            print("Current price: " + str(price['asks_vol']) + '\n')
            # save volumn record
            print("Saved Volumn: " + self.record_vol)

    def isBuyChance(self, symbol, result):
        # The checking rule is constructed by two parts:
        # 1. the current price must be higher than the last candle data
        # 2. there must be a continually increase of the trading volumn
        # In order to implement 2, following condition should be filled:
        # 2a. if trading volumn is n times bigger than average, the timestamp and volumn will be recorded
        # 2b. the recorded trading volumn will be added together with a weight factor
        # 2c. this weight factor is reduced very fast along the time (divide 1.5^time diff)
        # 2d. trading volumn condition is satisfied, if m volumn is recorded and the weighted average of them are still n times bigger than average
        # 2e. the recorded volumn will be removed, if it times weight factor is smaller than average volumn


        # 2a: if trading volumn is n times bigger than average
        if result[5] > self.average[5]*self.record_factor:
            print("Before volumn check:  ")
            print(self.record_vol)

            # save how many times is the recorded volumn and the recording timestamp
            record = [result[5]/self.average[5], time.time()]

            self.record_vol.append(record)
            # # check how many records are already exists. Remove the left one if the size is over defined
            # if len(self.record_vol) > self.record_number:
            #     self.record_vol.popleft()

            # update record volumn
            for i in range(len(self.record_vol)):
                # calculate time diff in minute
                time_diff = int((time.time() - self.record_vol[i][1])/60)
                # 2b,2c: recalculate the reocred volumn (factor) with a exponential function
                #TODO: more exact definition should be done for the decrease factor
                
                self.record_vol[i][0] = self.record_vol[i][0]/(self.alpha**time_diff)

            print("Between volumn check:  ")
            print(self.record_vol)

            # 2e: remove all record smaller than average (saved factor smaller than 1)
            self.record_vol = [x for x in self.record_vol if x[0]>1]

            print("After volumn check:  ")
            print(self.record_vol)

            # 2d: compare the record average with pre-defined record factor; check whether enough record is colleected
            weighted_avg = 0
            if len(self.record_vol)>self.record_number:
                weighted_avg = (numpy.mean(self.record_vol, axis=0)/len(self.record_vol))[0]
        
            print("Weigth is: ", weighted_avg)

            if weighted_avg > self.record_factor:
                return True
            else:
                return False

        return False

# symbol_list = ['ICXETH', 'EOSETH']

symbol_list = ['ADAETH','ADXETH','AEETH','AIONETH','AMBETH','APPCETH','ARKETH','ARNETH','ASTETH',
'BATETH','BCCETH','BCDETH','BCPTETH','BLZETH','BNBETH','BNTETH','BQXETH','BRDETH','BTGETH','BTSETH',
'CDTETH','CHATETH','CMTETH','CNDETH','CTRETH','DASHETH','DGDETH','DLTETH','DNTETH','EDOETH','ELFETH',
'ENGETH','ENJETH','EOSETH','ETCETH','EVXETH','FUELETH','FUNETH','GTOETH','GVTETH','GXSETH','HSRETH',
'ICNETH','ICXETH','INSETH','IOSTETH','IOTAETH','KMDETH','KNCETH','LENDETH','LINKETH','LRCETH','LSKETH',
'LTCETH','LUNETH','MANAETH','MCOETH','MDAETH','MODETH','MTHETH','MTLETH','NANOETH','NAVETH','NCASHETH',
'NEBLETH','NEOETH','NULSETH','OAXETH','OMGETH','ONTETH','OSTETH','PIVXETH','POAETH','POEETH','POWRETH',
'PPTETH','QSPETH','QTUMETH','RCNETH','RDNETH','REQETH','RLCETH','RPXETH','SALTETH','SNGLSETH','SNMETH',
'SNTETH','STEEMETH','STORJETH','STORMETH','STRATETH','SUBETH','TNBETH','TNTETH','TRIGETH','TRXETH','VENETH',
'VIAETH','VIBETH','VIBEETH','WABIETH','WAVESETH','WINGSETH','WTCETH','XLMETH','XMRETH','XRPETH','XVGETH',
'XZCETH','YOYOETH','ZECETH','ZILETH','ZRXETH']

print(len(symbol_list))

testlist = {}

begin_time = time.time()


print(time.time())

for symbol in symbol_list:
    print("Creation of the object ", symbol)
    testlist[symbol] = TradingChecker(symbol)

end_time = time.time()
time.sleep(end_time-begin_time)

while True:
    begin_time = time.time()

    for test in testlist:
        testlist[test].checkTradingChance()

    print("------------------ one cycle is completed @ ",str(datetime.fromtimestamp(time.time())), "--------------")

    end_time = time.time()

    # calculate how much time should be waiting for
    time_diff = end_time - begin_time
    print("Time usage in last round:", time_diff)
    # wait for the next candle cyclic
    time.sleep(300-time_diff)

# begin_time = time.time()
# end_time = time.time()

# while True:
#     begin_time = time.time()
#     print(begin_time)
#     for i in range(100000):
#         a = 1+i
#     end_time = time.time()
#     time.sleep(2-(end_time-begin_time))
#     # time.sleep(2)
    
#     if end_time == begin_time:
#         print("What the fuck!")
#     else:
#         print(round(end_time-begin_time,20))
#         print(end_time-begin_time)
#     print(end_time)
    
