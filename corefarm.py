from __future__ import with_statement

import math
import logging
import os.path
import re
import socket
import tarfile
import time
import urllib
import urllib2
import Blender
import simplejson

from hashlib import sha256

class PutRequest(urllib2.Request):
	def get_method(self):
		return 'PUT'


DEBUG_HTTP = False
COREFARM_API = 'http://gateway.corefarm.com/'
S3_HOST = 'http://corefarm-data.s3.amazonaws.com/'
USER_AGENT = 'Blender-Yafaray-Exporter/1.0'

S3_MIN_CHUNK_SIZE = 5 * 1024 * 1024 # 5 megabytes
S3_MAX_CHUNK_COUNT = 1024
S3_NUM_RETRIES = 3


if DEBUG_HTTP:
	import httplib
	httplib.HTTPConnection.debuglevel = 1

opener = urllib2.build_opener(
    urllib2.HTTPHandler(debuglevel = DEBUG_HTTP),
)



class CoreFarmError(RuntimeWarning): pass
class AccessForbiddenError(CoreFarmError): pass

class StaticFarm(object):
	HEADERS = {
		'User-Agent': USER_AGENT,
		} 
	
	def __init__(self, login, key, output_type):
		self._login = login
		self._key = key
		self._output_type = output_type
		self._log = logging.getLogger('yafaray.export')

# Sign requests according to the algorithm defined on the corefarm		
	def _sign(self, method, data):
		""" Returns the same data dict with
			two additional items: login and signature
		"""
		data = data.copy()
		joined = method + ''.join(
			'='.join(item)
			for item in sorted(data.items())
		) + self._login + self._key

		self._log.debug('Joined data to hash: %r' % joined)

		hash = sha256(joined)
		data['login'] = self._login
		data['signature'] = hash.hexdigest()
		return data

	def get_new_job(self): 
		self._log.debug('Getting a new job id.')
		socket.setdefaulttimeout(10)
		method = 'new_job'
		parameters = self._sign(
			method,
			dict(
				application = 'yafaray',
				date = str(int(time.time())),
				isconfidential = 'true',
			)
		)
		url = '%s%s?%s' % (
			COREFARM_API,
			method,
			urllib.urlencode(parameters)
		)

		self._log.debug('Fetching the URL: %r' % url)
		request = urllib2.Request(url, headers = self.HEADERS)
		result = opener.open(request).read()

		self._log.debug('Result is: %r' % result)
		result = simplejson.loads(result)

		if 'msg' in result:
			if 'forbidden' in result['msg'].lower():
				raise AccessForbiddenError(result['msg'])
			else:
				raise CoreFarmError(result['msg'])
		elif 'id' in result:
			return result['id']
		else:
			raise RuntimeError('Unknown result from the server')

# vim:noexpandtab
