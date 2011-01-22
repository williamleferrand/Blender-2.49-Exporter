from __future__ import with_statement

import math
import logging
import os.path
import re
import socket
import gzip
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


# UPLOAD MECHANISM 
	def _upload_part(self, data, part_number, key, upload_id):
		for attempt in xrange(S3_NUM_RETRIES):
			try:
				request = urllib2.Request(
					COREFARM_API + 'request_signature?' + urllib.urlencode(dict(
							method = 'put',
							content_type = 'application/binary',
							key = '%(key)s?partNumber=%(part_number)s&uploadId=%(upload_id)s' % locals()
						)
					),
					headers = self.HEADERS
				)
				signature = opener.open(request).read()

				request = PutRequest(
					S3_HOST + key + '?' + urllib.urlencode(dict(
						partNumber = str(part_number),
						uploadId = str(upload_id),
					)) + '&' + signature,
					data,
					headers = dict(self.HEADERS, **{
						'Content-Type': 'application/binary',
					})
				)
				result = opener.open(request)
				return result.headers['etag']
			except (urllib2.URLError, urllib2.HTTPError), e:
				pass
		raise

	def upload (self, job_id, datafile, compress = False): 
		self._log.debug('Uploading file to S3')

		filename = datafile 

		if compress:
			filename = datafile + '.gz'
			f_in = open(datafile, 'rb')
			f_out = gzip.open(filename, 'wb')
			f_out.writelines(f_in)
			f_out.close()
			f_in.close()

		key = '%s/%s' % (job_id, os.path.basename(filename))
		request = urllib2.Request(
			COREFARM_API + 'initiate_multipart?' + urllib.urlencode(dict(key=key)),
			headers = self.HEADERS,
		)
		result = opener.open(request).read()
		json = simplejson.loads(result)
		if json['status'] != 1:
			raise RuntimeError(result)
		upload_id = json['msg']
		etags = {}

		with open(filename, 'rb') as file:
			file.seek(0, 2)
			file_size = file.tell()
			file.seek(0)

			chunk_size = max(S3_MIN_CHUNK_SIZE, file_size / S3_MAX_CHUNK_COUNT)
			num_parts = int(math.ceil(file_size / float(chunk_size)))
			self._log.debug('Chunk size is %s, num chunks is %s' % (chunk_size, num_parts))

			part_number = 1
			data = file.read(chunk_size)
			while data:
				self._log.debug('UPLOADING PART %s' % part_number)
				etags[part_number] = self._upload_part(data, part_number, key, upload_id)

				Blender.Window.DrawProgressBar(num_parts / part_number, "Uploading the data ...")
				data = file.read(chunk_size)
				part_number += 1
			file.close () 

		if compress:
			os.remove(filename)
				

		self._log.debug('Finalizing upload')
		data = '<CompleteMultipartUpload>'
		for item in etags.iteritems():
		  data += '<Part><PartNumber>%s</PartNumber><ETag>%s</ETag></Part>' % item
		data += '</CompleteMultipartUpload>'

		request = urllib2.Request(
			COREFARM_API + 'request_signature?' + urllib.urlencode(dict(
					method = 'post',
					content_type = 'application/xml',
					key = '%(key)s?uploadId=%(upload_id)s' % locals()
				)
			),
			headers = self.HEADERS,
		)
		signature = opener.open(request).read()

		request = urllib2.Request(
			S3_HOST + key + '?' + urllib.urlencode(dict(
				uploadId = str(upload_id),
			)) + '&' + signature,
			data,
			headers = dict(self.HEADERS, **{
				'content-type': 'application/xml',
			})
		)
		result = opener.open(request)

		if result and result.code != 200:
			self._log.debug('Response from S3: %r' % result)
