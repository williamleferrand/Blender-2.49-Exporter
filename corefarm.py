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
		self._ghz = 10
		self._output_type = output_type
		self._log = logging.getLogger('yafaray.export')


	def render(self, xml_filename):
		try:
			Blender.Window.DrawProgressBar(0.0, "Packing the data ...")
			datafile = self._pack_data(xml_filename)

			Blender.Window.DrawProgressBar(1.0, "Creating a job ...")
			job_id = self._get_new_job()

			if job_id:
				self._upload(job_id, datafile)


				Blender.Window.DrawProgressBar(0.0, "Starting render on the farm ...")

				self._start_job(job_id)

				Blender.Window.DrawProgressBar(1.0, "Done")
				self._log.debug('Done')
		except urllib2.HTTPError, e:
			self._log.exception('HTTPError: %r' % e.read())
			Blender.Draw.PupMenu('Service is unavailable, please, try later.')
		except IOError, e:
			Blender.Window.DrawProgressBar(1.0, "Done with warning")
			if e.errno == 'socket error':
				Blender.Draw.PupMenu('Service is unavailable, please try later.')
			else:
				raise
		except CoreFarmError, e:
			Blender.Draw.PupMenu(unicode(e))
			Blender.Window.DrawProgressBar(1.0, "Done with warning")
			if isinstance(e, AccessForbiddenError):
				""" Reraise exception to handle it in the event loop.
				"""
				raise
		except Exception:
			self._log.exception('render failed')
			Blender.Window.DrawProgressBar(1.0, "Done with error")
			raise


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


	def _get_new_job(self):
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


	def _start_job(self, job_id):
		self._log.debug('Starting the job: %r' % job_id)
		socket.setdefaulttimeout(10)
		method = 'start_job'
		parameters = self._sign(
			method,
			dict(
				job_id = str(job_id),
				ghz = str(self._ghz),
				date = str(int(time.time())),
				input = '$scene.xml$ %s' % self._output_type,
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
			if result['msg'] == 'success':
				Blender.Draw.PupMenu('Your job is now running. You can track its status from your manager on www.corefarm.com; you will also receive an email when it is completed. Thanks!')
			else:
				raise CoreFarmError(result['msg'])
		else:
			raise RuntimeError('Unknown result from the server')

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

	def _upload(self, job_id, datafile):
		Blender.Window.DrawProgressBar(0.0, "Uploading the data ...")

		self._log.debug('Uploading file to S3')
		key = '%s/%s' % (job_id, os.path.basename(datafile))
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

		with open(datafile, 'rb') as file:
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

		os.remove(datafile)

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

		Blender.Window.DrawProgressBar(1.0, "Uploading the data ...")

	def _pack_data(self, xml_filename):
		self._log.debug('Packing filename %r along with textures.' % (xml_filename,))
		start = time.time()

		base_xml_filename = xml_filename.rsplit(os.path.extsep, 1)[0]
		relative_xml_filename = base_xml_filename + '-relative.xml'

		files = [
			(relative_xml_filename, 'scene.xml')
		]

		def make_path_local(match):
			full_path = match.group(2)
			local_path = os.path.basename(full_path)
			files.append((full_path, local_path))
			return match.group(1) + local_path

		with open(xml_filename) as input:
			with open(relative_xml_filename, 'w') as output:
				for line in input:
					output.write(
						re.sub(
							r'(filename sval=")([^"]*)',
							make_path_local,
							line
						)
					)
		tar_filename = base_xml_filename + '.tar.gz'
		tar = tarfile.TarFile.open(tar_filename, mode = 'w|gz')

		try:
			for full_path, archive_path in files:
				if os.path.exists(full_path):
					tar.add(full_path, archive_path, recursive = False)
				else:
					self._log.warning('File "%s" not found.' % full_path)
		finally:
			tar.close()

		self._log.debug('Packing done in %s seconds' % (time.time() - start))
		os.remove(xml_filename)
		os.remove(relative_xml_filename)
		return tar_filename

# vim:noexpandtab
