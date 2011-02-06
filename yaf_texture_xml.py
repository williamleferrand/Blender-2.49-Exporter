import Blender.Texture
import re
import os
# ------------------------------------------------------------------------
#
# Textures
#
# ------------------------------------------------------------------------

def noise2string(ntype):
	if ntype == Blender.Texture.Noise.BLENDER:			return "blender"
	elif ntype == Blender.Texture.Noise.PERLIN:			return "stdperlin"
	elif ntype == Blender.Texture.Noise.IMPROVEDPERLIN: return "newperlin"
	elif ntype == Blender.Texture.Noise.VORONOIF1:		return "voronoi_f1"
	elif ntype == Blender.Texture.Noise.VORONOIF2:		return "voronoi_f2"
	elif ntype == Blender.Texture.Noise.VORONOIF3:		return "voronoi_f3"
	elif ntype == Blender.Texture.Noise.VORONOIF4:		return "voronoi_f4"
	elif ntype == Blender.Texture.Noise.VORONOIF2F1:	return "voronoi_f2f1"
	elif ntype == Blender.Texture.Noise.VORONOICRACKLE:	return "voronoi_crackle"
	elif ntype == Blender.Texture.Noise.CELLNOISE:		return "cellnoise"
	return "newperlin"

def get_image_filename(tex,blenderlib):
	""" Get the true image filename for the current frame
	This is needed because blender do not update any information
	in the image object to indicate the true filename of an image sequence
	"""
	ima = tex.getImage()
	if blenderlib:
		# Image path (absolute or relative to the library blend file)
		libdir = Blender.sys.expandpath(Blender.sys.dirname(blenderlib)) # library absolute dir
		imgrelpath = Blender.sys.relpath(ima.getFilename(),Blender.sys.expandpath(blenderlib)) # image relative path against library
		imagepath = libdir + Blender.sys.sep + imgrelpath
	else:
		imagepath = Blender.sys.expandpath(ima.getFilename())

	if ima.source == Blender.Image.Sources['SEQUENCE']:
		currentframe = Blender.Scene.GetCurrent().getRenderingContext().currentFrame()
		startframe = tex.animStart
		numframes = tex.animFrames
		offset = tex.animOffset
		if tex.cyclic:
			currentframe = ((currentframe-startframe+offset) % numframes) + 1
		else:
			if currentframe in range(startframe, startframe + numframes):
				currentframe += offset - (startframe - 1)
			else:
				if currentframe >= startframe+numframes:
					currentframe = offset - (startframe - 1)
				elif currentframe < startframe:
					currentframe = offset - startframe
		regex = re.compile(r'^(.*?)([0-9]*)$')
		dname = Blender.sys.dirname(Blender.sys.expandpath(ima.getFilename()))
		fname = Blender.sys.splitext(Blender.sys.basename(ima.getFilename()))
		seqname = regex.match(fname[0]).group(1)
		for imgfile in os.listdir(dname):
			basename = Blender.sys.splitext(imgfile)[0]
			seqname2 = regex.match(basename).group(1)
			seqnum2 = regex.match(basename).group(2)
			if seqname == seqname2 and int(seqnum2) == currentframe:
				imagepath = Blender.sys.join(dname, seqname + seqnum2 + fname[1])
				break;
	return imagepath
class yafTexture:
	def __init__(self, interface):
		self.yi = interface

	def namehash(self,obj):
		# TODO: Better hashing using mat.__str__() ?
		nh = obj.name + "." + str(obj.__hash__())
		return nh
		
	def writeTexture(self, tex, name, job_id, blenderlib=None, gamma=1.8):
		yi = self.yi
		yi.paramsClearAll()
		
		nsz = tex.noiseSize
		if nsz > 0: nsz = 1.0/nsz
		hard = False
		if tex.noiseType == "hard": hard = True
		
		if tex.type == Blender.Texture.Types.BLEND:
			yi.printInfo("Exporter: Creating Texture: \"" + name + "\" type BLEND")
			yi.paramsSetString("type", "blend")
			stype = "lin"
			if tex.stype == Blender.Texture.STypes.BLN_LIN:		stype = "lin"
			elif tex.stype == Blender.Texture.STypes.BLN_QUAD:	stype = "quad"
			elif tex.stype == Blender.Texture.STypes.BLN_EASE:	stype = "ease"
			elif tex.stype == Blender.Texture.STypes.BLN_DIAG:	stype = "diag"
			elif tex.stype == Blender.Texture.STypes.BLN_SPHERE:	stype = "sphere"
			elif tex.stype == Blender.Texture.STypes.BLN_HALO:	stype = "halo"
			yi.paramsSetString("stype", stype)
		elif tex.type == Blender.Texture.Types.CLOUDS:
			yi.printInfo("Exporter: Creating Texture: \"" + name + "\" type CLOUDS")
			yi.paramsSetString("type", "clouds")
			yi.paramsSetFloat("size", nsz)
			yi.paramsSetBool("hard", hard)
			yi.paramsSetInt("depth", tex.noiseDepth)
			#yi.paramsSetInt("color_type", tex->stype); # unused?
			yi.paramsSetString("noise_type", noise2string(tex.noiseBasis))
		elif tex.type == Blender.Texture.Types.WOOD:
			yi.printInfo("Exporter: Creating Texture: \"" + name + "\" type WOOD")
			yi.paramsSetString("type", "wood")
			# blender does not use depth value for wood, always 0
			yi.paramsSetInt("depth", 0)
			turb = 0.0
			if tex.stype >= 2: turb = tex.turbulence
			yi.paramsSetFloat("turbulence", turb)
			yi.paramsSetFloat("size", nsz)
			yi.paramsSetBool("hard", hard )
			ts = "bands"
			if tex.stype == Blender.Texture.STypes.WOD_RINGS or tex.stype == Blender.Texture.STypes.WOD_RINGNOISE:
				ts = "rings"
			yi.paramsSetString("wood_type", ts )
			yi.paramsSetString("noise_type", noise2string(tex.noiseBasis))
			# shape parameter, for some reason noisebasis2 is used...
			ts = "sin"
			if tex.noiseBasis2==1: ts="saw"
			elif tex.noiseBasis2==2: ts="tri"
			yi.paramsSetString("shape", ts )
		elif tex.type == Blender.Texture.Types.MARBLE:
			yi.printInfo("Exporter: Creating Texture: \"" + name + "\" type MARBLE")
			yi.paramsSetString("type", "marble")
			yi.paramsSetInt("depth", tex.noiseDepth)
			yi.paramsSetFloat("turbulence", tex.turbulence)
			yi.paramsSetFloat("size", nsz)
			yi.paramsSetBool("hard", hard )
			yi.paramsSetFloat("sharpness", float(1<<tex.stype))
			yi.paramsSetString("noise_type", noise2string(tex.noiseBasis))
			ts = "sin"
			if tex.noiseBasis2==1: ts="saw"
			elif tex.noiseBasis2==2: ts="tri"
			yi.paramsSetString("shape", ts)
		elif tex.type == Blender.Texture.Types.VORONOI:
			yi.printInfo("Exporter: Creating Texture: \"" + name + "\" type VORONOI")
			yi.paramsSetString("type", "voronoi")
			ts = "int"
			# vn_coltype not available in python, but types are listed for STypes, so it's a guess!
			if tex.stype == Blender.Texture.STypes.VN_COL1:		ts = "col1" 
			elif tex.stype == Blender.Texture.STypes.VN_COL2:	ts = "col2"
			elif tex.stype == Blender.Texture.STypes.VN_COL3:	ts = "col3"
			yi.paramsSetString("color_type", ts)
			yi.paramsSetFloat("weight1", tex.weight1)
			yi.paramsSetFloat("weight2", tex.weight2)
			yi.paramsSetFloat("weight3", tex.weight3)
			yi.paramsSetFloat("weight4", tex.weight4)
			yi.paramsSetFloat("mk_exponent", tex.exp)
			yi.paramsSetFloat("intensity", tex.iScale)
			yi.paramsSetFloat("size", nsz)
			ts = "actual"
			if tex.distMetric == 1: 	ts = "squared"
			elif tex.distMetric == 2:	ts = "manhattan"
			elif tex.distMetric == 3:	ts = "chebychev"
			elif tex.distMetric == 4:	ts = "minkovsky_half"
			elif tex.distMetric == 5:	ts = "minkovsky_four"
			elif tex.distMetric == 6:	ts = "minkovsky"
			yi.paramsSetString("distance_metric", ts)
		elif tex.type == Blender.Texture.Types.MUSGRAVE:
			yi.printInfo("Exporter: Creating Texture: \"" + name + "\" type MUSGRAVE")
			yi.paramsSetString("type", "musgrave")
			ts = "fBm"
			if tex.stype == Blender.Texture.STypes.MUS_MFRACTAL:
				ts = "multifractal"
			elif tex.stype == Blender.Texture.STypes.MUS_RIDGEDMF:
				ts = "ridgedmf"
			elif tex.stype == Blender.Texture.STypes.MUS_HYBRIDMF:
				ts = "hybridmf"
			elif tex.stype == Blender.Texture.STypes.MUS_HYBRIDMF:
				ts = "heteroterrain"
			yi.paramsSetString("musgrave_type", ts)
			yi.paramsSetString("noise_type", noise2string(tex.noiseBasis))
			yi.paramsSetFloat("H", tex.hFracDim)
			yi.paramsSetFloat("lacunarity", tex.lacunarity)
			yi.paramsSetFloat("octaves", tex.octs)
		# can't find these values in Python API docs...
		#	if ((tex->stype==TEX_HTERRAIN) || (tex->stype==TEX_RIDGEDMF) || (tex->stype==TEX_HYBRIDMF)) {
		#		yG->paramsSetFloat("offset", tex->mg_offset);
		#		if ((tex->stype==TEX_RIDGEDMF) || (tex->stype==TEX_HYBRIDMF))
		#			yG->paramsSetFloat("gain", tex->mg_gain);
		#	}
			yi.paramsSetFloat("size", nsz)
			yi.paramsSetFloat("intensity", tex.iScale)
		elif tex.type == Blender.Texture.Types.DISTNOISE:
			yi.printInfo("Exporter: Creating Texture: \"" + name + "\" type DISTORTED NOISE")
			yi.paramsSetString("type", "distorted_noise")
			yi.paramsSetFloat("distort", tex.distAmnt)
			yi.paramsSetFloat("size", nsz)
			yi.paramsSetString("noise_type1", noise2string(tex.noiseBasis))
			yi.paramsSetString("noise_type2", noise2string(tex.noiseBasis2))
		elif tex.type == Blender.Texture.Types.IMAGE:
			ima = tex.getImage()
			if ima != None:
				# get image full path
				imagefile = get_image_filename(tex,blenderlib)
				yi.printInfo("Exporter: Creating Texture: \"" + name + "\" type IMAGE: " + imagefile)
				# remember image to avoid duplicates later if also in imagetex
				# (formerly done by removing from imagetex, but need image/material link)
				#	dupimg.insert(ima);
				key = '%s/input/%s' % (job_id, os.path.basename(imagefile))
				yi.paramsSetString("type", "image")
				yi.paramsSetString("filename", key)
			#	yG->paramsSetString("interpolate", (tex->imaflag & TEX_INTERPOL) ? "bilinear" : "none");
				yi.paramsSetFloat("gamma", gamma)
				yi.paramsSetBool("use_alpha", tex.useAlpha > 0)
				yi.paramsSetBool("calc_alpha", tex.calcAlpha > 0)
				yi.paramsSetBool("normalmap", tex.normalMap > 0)
						
				# repeat
				yi.paramsSetInt("xrepeat", tex.repeat[0])
				yi.paramsSetInt("yrepeat", tex.repeat[1])
						
				# clipping
				ext = tex.extend
				
				#print tex.getExtend()
				if ext == Blender.Texture.ExtendModes.EXTEND: yi.paramsSetString("clipping", "extend")
				elif ext == Blender.Texture.ExtendModes.CLIP:	yi.paramsSetString("clipping", "clip")
				elif ext == Blender.Texture.ExtendModes.CLIPCUBE:	yi.paramsSetString("clipping", "clipcube")
				elif tex.getExtend() == "Checker": #Blender.Texture.ExtendModes.CHECKER:
					yi.paramsSetString("clipping", "checker")
					yi.paramsSetBool("even_tiles", tex.flags & Blender.Texture.Flags.CHECKER_EVEN)
					yi.paramsSetBool("odd_tiles", tex.flags & Blender.Texture.Flags.CHECKER_ODD)
				else: yi.paramsSetString("clipping", "repeat")
				
				# crop min/max
				yi.paramsSetFloat("cropmin_x", tex.crop[0])
				yi.paramsSetFloat("cropmin_y", tex.crop[1]) # no idea of order in tupel :(
				yi.paramsSetFloat("cropmax_x", tex.crop[2])
				yi.paramsSetFloat("cropmax_y", tex.crop[3])
				
				# rot90 flag
				if tex.rot90 != 0:
					yi.paramsSetBool("rot90", True)
		
		yi.createTexture(name)
	
