""" Volatility tool.

	Fetches historical data from binance and inspects the volatility of symbols
	by looking at how many times they hit highs and lows.
"""

from binance.client import Client
from binance.exceptions import BinanceAPIException
import argparse
import json
import os
import sys

client = None


class Kline(object):
	""" Candlestick bar for a symbol. """

	def __init__(self, values):
		""" Kline wrapper for this format

			[
				1499040000000,      // Open time
				"0.01634790",       // Open
				"0.80000000",       // High
				"0.01575800",       // Low
				"0.01577100",       // Close
				"148976.11427815",  // Volume
				1499644799999,      // Close time
				"2434.19055334",    // Quote asset volume
				308,                // Number of trades
				"1756.87402397",    // Taker buy base asset volume
				"28.46694368",      // Taker buy quote asset volume
				"17928899.62484339" // Ignore
			]
		"""

		self.open_time, self.open, self.high, self.low, self.close, self.volume, \
			self.close_time, self.quote_asset_volume, self.trades, self.taker_base_volume, \
			self.taker_quote_volume, _ = values

		self.open = float(self.open)
		self.high = float(self.high)
		self.low = float(self.low)
		self.close = float(self.close)
		self.volume = float(self.volume)
		self.quote_asset_volume = float(self.quote_asset_volume)
		self.taker_base_volume = float(self.taker_base_volume)
		self.taker_quote_volume = float(self.taker_quote_volume)


class Volatility(object):
	""" Volatility representation of a symbol. """

	def __init__(self, symbol, thresholds):
		""" Configure the volatility object with a table of price thresholds (in %)
			that will be used to detect the number of times the price goes past these thresholds.
		"""

		self.symbol = symbol
		self.thresholds = thresholds

	@staticmethod
	def get(symbol, interval, period):
		""" Build a volatility object by fetching and parsing historical klines. """

		# fetch 1 minute klines for the last hour up until now
		try:
			klines = client.get_historical_klines(symbol, interval, "%s ago UTC" % (period))
		except BinanceAPIException as e:
			print e
			sys.exit(1)

		klines = [Kline(bar) for bar in klines]

		# print 'Kline closes: ' + '\n'.join([str(k.close) for k in klines])
		return Volatility.from_klines(symbol, interval, klines)

	@staticmethod
	def from_klines(symbol, interval, klines):
		""" Build a volatility object by parsing historical klines. """

		volatility_thresholds = [0.30, 0.25, 0.20, 0.15, 0.10, 0.05, 0.04, 0.03, 0.02, 0.01, 0.005, 0.0025]
		# volatility_thresholds = [0.02, 0.01]
		closes = [k.close for k in klines]

		vol = Volatility(symbol, thresholds=volatility_thresholds)
		vol.symbol = symbol
		vol.interval = interval
		vol.min_close = min(closes)
		vol.max_close = max(closes)
		vol.avg_close = sum(closes) / len(closes)
		vol.high_hits = {threshold: Volatility.hits_over_threshold(vol.avg_close, threshold, klines) for threshold in vol.thresholds}
		# print '\n----\n'
		vol.low_hits = {threshold: Volatility.hits_over_threshold(vol.avg_close, -threshold, klines) for threshold in vol.thresholds}
		return vol

	@staticmethod
	def hits_over_threshold(avg_close, threshold, klines):
		""" Count the number of times the close price went above or below the threshold.
			This tries to count the number of peaks, not the number of bars over the threshold.
		"""

		def gt_operator(a, b):
			return a > b

		def lt_operator(a, b):
			return a < b

		comp_operator = gt_operator if threshold > 0 else lt_operator

		close_threshold = avg_close * (1.0 + threshold)
		count = 0
		is_over_threshold = False
		for k in klines:
			# print 'close: %f, close_threshold: %f' % (k.close, close_threshold)
			if comp_operator(k.close, close_threshold):
				# print '  over!'
				if not is_over_threshold:
					# print '    +1 at %f' % (threshold)
					is_over_threshold = True
					count += 1
			else:
				is_over_threshold = False

		# print '\n'
		return count

	def print_summary(self):
		""" Print a summary of the volatility information of a symbol. """

		change_pct = (self.max_close / self.min_close) * 100.0 - 100.0
		headline = '%s volatility information' % (self.symbol)
		print headline + '\n' + ('-' * len(headline)) + '\n'
		print 'Price: min: %f, max %f, avg: %f, change: %.2f%%\n' % (self.min_close, self.max_close, self.avg_close, change_pct)
		table = ''
		for threshold in self.thresholds:
			if self.high_hits[threshold] > 0.0 or self.low_hits[threshold] > 0.0:
				table += '+{:8.2f}% | {:4d} | -{:8.2f}% | {:4d}\n'.format(float(threshold * 100), self.high_hits[threshold], threshold * 100, self.low_hits[threshold])

		if table:
			header = '+THRESHOLD | HITS | -THRESHOLD | HITS'
			print header + '\n' + '-' * len(header)
			print table


def load_credentials():
	""" Load the client credentials from the credentials.secret that must be in the same folder as this script """

	try:
		credentials_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'credentials.secret')
		with open(credentials_path) as f:
			credentials = json.load(f)
	except Exception:
		print 'Failed to load credentials at %s' % credentials_path
		sys.exit(1)
	return credentials

if __name__ == '__main__':
	parser = argparse.ArgumentParser()
	parser.add_argument('-s', '--symbols', help='One or more symbol pairs to calculate recent volatility for (i.e. APPCBTC, or APPCBTC+MTHBTC+BNBBTC)', required=True)
	parser.add_argument('-i', '--interval', help='The tick interval of candlesticks (i.e. 1m)', required=True)
	parser.add_argument('-p', '--period', help='The period up until now to calculate volatility for (i.e. "1 day", "1 hour")', required=True)
	args = parser.parse_args()

	credentials = load_credentials()
	client = Client(credentials['key'], credentials['secret'])

	symbols = args.symbols.split('+')
	for symbol in symbols:
		vol = Volatility.get(symbol, args.interval, args.period)
		vol.print_summary()
