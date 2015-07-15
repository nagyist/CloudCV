# encoding: utf-8
from django.views.generic import CreateView
from django.http import HttpResponse, HttpResponseRedirect
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render

from django.http import HttpResponse, HttpResponseRedirect
from django.views.generic import CreateView, DeleteView
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import render
from .response import JSONResponse, response_mimetype
from .serialize import serialize
from django.conf import settings
from PIL import Image
from io import BytesIO

from app.celery.web_tasks.ImageStitchingTask import runImageStitching
from app.models import Picture, RequestLog, Decaf
from app.core.job import Job
from querystring_parser import parser
from log import logger, log, log_to_terminal, log_and_exit
from savefile import saveFilesAndProcess
import app.thirdparty.dropbox_auth as dbauth
import app.thirdparty.google_auth as gauth

import app.conf as conf
import base64
import redis
import decaf_views
import StringIO
import time
import subprocess
import os
import json
import traceback
import uuid
import datetime
import shortuuid
import redis

r = redis.StrictRedis(host=config.REDIS_HOST, port=6379, db=0)


class Request:
    socketid = None

    def run_executable(self, src_path, output_path, result_path):
        stitchImages.delay(src_path, self.socketid, output_path, result_path)

    def log_to_terminal(self, message):
        r.publish('chat', json.dumps({'message': str(message), 'socketid': str(self.socketid)}))


def run_executable(list, session, socketid, ):
        try:

            popen=subprocess.Popen(list,stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            count=1

            while True:
                popen.poll()
                if(popen.stdout):
                    line=popen.stdout.readline()
                    popen.stdout.flush()

                if(popen.stderr):
                   errline=popen.stdout.readline()
                   popen.stderr.flush()


                if line:
                    r.publish('chat', json.dumps({'message': str(line), 'socketid': str(socketid)}))
                    print count,line, '\n'
                    count += 1

                if errline:
                    r.publish('chat', json.dumps({'message': str(errline), 'socketid': str(socketid)}))
                    print count,line, '\n'
                    count += 1

                if line == '':
                    break
            r.publish('chat', json.dumps({'message': str('Thank you for using CloudCV'), 'socketid': str(socketid)}))

        except Exception as e:
            r.publish('chat', json.dumps({'message': str(traceback.format_exc()), 'socketid': str(socketid)}))
        return '\n', '\n'


class PictureCreateView(CreateView):
    model = Picture

    def form_valid(self, form):
        """
        Method for checking the django form validation and then saving 
        the images after resizing them.  
        """
        try:
            request_obj = Request()

            request_obj.socketid = self.request.POST['socketid-hidden']
            self.object = form.save()
            serialize(self.object)
            data = {'files': []}

            old_save_dir = os.path.dirname(conf.PIC_DIR)

            folder_name = str(shortuuid.uuid())
            save_dir = os.path.join(conf.PIC_DIR, folder_name)

            # Make the new directory based on time
            if not os.path.exists(save_dir):
                os.makedirs(save_dir)
                os.makedirs(os.path.join(save_dir, 'results'))

            all_files = self.request.FILES.getlist('file')

            for file in all_files:
                log_to_terminal(str('Saving file:' + file.name), request_obj.socketid)
                a = Picture()
                tick = time.time()
                strtick = str(tick).replace('.', '_')
                fileName, fileExtension = os.path.splitext(file.name)
                file.name = fileName + strtick + fileExtension
                a.file.save(file.name, file)

                file.name = a.file.name

                # imgstr = base64.b64encode(file.read())
                # img_file = Image.open(BytesIO(base64.b64decode(imgstr)))
                # img_file.thumbnail(size, Image.ANTIALIAS)
                imgfile = Image.open(os.path.join(old_save_dir, file.name))
                size = (500, 500)
                imgfile.thumbnail(size, Image.ANTIALIAS)

                imgfile.save(os.path.join(save_dir, file.name))
                thumbPath = os.path.join(folder_name, file.name)
                data['files'].append({
                    'url': conf.PIC_URL + thumbPath,
                    'name': file.name,
                    'type': 'image/png',
                    'thumbnailUrl': conf.PIC_URL + thumbPath,
                    'size': 0,
                })

            request_obj.run_executable(save_dir, os.path.join(save_dir, 'results/'),
                                       os.path.join(conf.PIC_URL, folder_name, 'results/result_stitch.jpg'))

            response = JSONResponse(data, mimetype=response_mimetype(self.request))
            response['Content-Disposition'] = 'inline; filename=files.json'

            return response
        except:
            r.publish('chat', json.dumps({'message': str(traceback.format_exc()), 'socketid': str(self.socketid)}))


class BasicPlusVersionCreateView(PictureCreateView):
    template_name_suffix = '_basicplus_form'


def homepage(request):
    """
    View for home page
    """
    return render(request, 'index.html')


def ec2(request):
    """
    This functionality is deprecated. We need to remove it from the codebase. 
    """
    token = request.GET['dropbox_token']
    emailid = request.GET['emailid']

    dirname = str(uuid.uuid4())
    result_path = '/home/cloudcv/detection_executable/detection_output/' + dirname + '/'

    list = ['starcluster', 'sshmaster', 'demoCluster',
            'cd /home/cloudcv/detection_executable/PascalImagenetDetector/distrib; '
            'mkdir ' + result_path + ';' +
            'qsub run_one_category.sh ' + result_path]

    popen = subprocess.Popen(list, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    complete_output = ''
    count = 0
    errline = ''
    line = ''

    while popen.poll() is None:
        if popen.stdout:
            line = popen.stdout.readline()
            popen.stdout.flush()

        if popen.stderr:
            errline = popen.stdout.readline()
            popen.stderr.flush()

        if line:
            print count, line, '\n'
            complete_output += str(line)
            count += 1

        if errline:
            print count, errline, '\n'
            complete_output += str(errline)
            count += 1

    complete_output += result_path
    list = ['starcluster', 'sshmaster', 'demoCluster',
            'cd /home/cloudcv/detection_executable/PascalImagenetDetector/distrib; '
            'python sendJobs1.py ' + token + ' ' + emailid + ' ' + result_path + ' ' + dirname + ';']
    popen = subprocess.Popen(list, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
    popen.communicate()
    return HttpResponse(complete_output)


@csrf_exempt
def demoUpload(request, executable):
    """
    Method called when the image stitching of demo images is done by 
    clicking on the button 'Submit these' at /image-stitch url.   
    """
    try:
        if request.method == 'POST':

            request_obj = Request()

            if 'socketid-hidden' in request.POST:
                request_obj.socketid = request.POST['socketid-hidden']

            print request_obj.socketid
            data = []
            save_dir = os.path.join(conf.LOCAL_DEMO1_PIC_DIR)

            request_obj.log_to_terminal(str('Images Processed. Starting Executable'))
            request_obj.run_executable(save_dir, os.path.join(save_dir, 'results/'),
                                       '/app/media/pictures/demo1/results/result_stitch.jpg')

            data.append({'text': str('')})
            data.append({'result': '/app/media/pictures/demo/output/result_stitch.jpg'})
            response = JSONResponse(data, {}, response_mimetype(request))
            response['Content-Disposition'] = 'inline; filename=files.json'
            return response

    except Exception as e:
        return HttpResponse(str(e))

    return HttpResponse('Not a post request')


def log_every_request(job_obj):
    """
    Method for logging. 
    """
    try:
        now = datetime.datetime.utcnow()
        req_obj = RequestLog(cloudcvid=job_obj.userid, noOfImg=job_obj.count,
                             isDropbox=job_obj.isDropbox(), apiName=None,
                             function=job_obj.executable, dateTime=now)
        req_obj.save()
    except:
        r = redis.StrictRedis(host=config.REDIS_HOST, port=6379, db=0)
        r.publish('chat', json.dumps({'error': str(traceback.format_exc()), 'socketid': job_obj.socketid}))


@csrf_exempt
def matlabReadRequest(request):
    """
    Method that makes request to the matlab api. 
    """
    if request.method == 'POST':    # post request
        post_dict = parser.parse(request.POST.urlencode())

        try:
            job_obj = Job(params_obj=post_dict)
            log_to_terminal('Server: Post Request Recieved', job_obj.socketid)
            response = saveFilesAndProcess(request, job_obj)

        except:
            log_and_exit(str(traceback.format_exc()), job_obj.socketid)
            return HttpResponse('Error at server side')

        return HttpResponse(str(response))

    else:
        response = JSONResponse({}, {}, response_mimetype(request))
        response['Content-Disposition'] = 'inline; filename=files.json'
        return response


def authenticate(request, auth_name):
    """
    Authentication method: Currently used for Python API.
    """
    if auth_name == 'dropbox':
        is_API = 'type' in request.GET and request.GET['type'] == 'api'
        contains_UUID = 'userid' in request.GET

        str_response = dbauth.handleAuth(request, is_API, contains_UUID)

        # if the call comes from Matlab or Python API, send the obtained JSON string
        if is_API:
            return HttpResponse(str_response)

        # else if it comes from browser - redirect the browser
        else:
            return HttpResponseRedirect(str_response)

    if auth_name == 'google':
        is_API = 'type' in request.GET and request.GET['type'] == 'api'
        contains_UUID = 'userid' in request.GET

        str_response = gauth.handleAuth(request, is_API, contains_UUID)

        # if the call comes from Matlab or Python API, send the obtained JSON string
        if is_API:
            return HttpResponse(str_response)

        # else if it comes from browser - redirect the browser
        else:
            return HttpResponseRedirect(str_response)

    # Invalid URL if its not one of the above authentication system
    return HttpResponse('Invalid URL')


@csrf_exempt
def callback(request, auth_name):
    """
    Callback method associated with authentication part. 
    """
    if auth_name == 'dropbox':
        post_dict = parser.parse(request.POST.urlencode())
        code = str(post_dict['code'])
        userid = str(post_dict['userid'])
        json_response = dbauth.handleCallback(userid, code, request)
        return HttpResponse(json_response)

    if auth_name == 'google':
        post_dict = parser.parse(request.POST.urlencode())
        code = str(post_dict['code'])
        json_response = gauth.handleCallback(code, request)
        return HttpResponse(json_response)

    return HttpResponse('Invalid URL')

####################################################################

from rest_framework.views import APIView
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import Http404
from rest_framework import generics
from serializers import *


class CloudCV_UserList(APIView):
  """
  List all cloudcv users, or create a new user.
  """
  def get(self, request, format=None):
      cloudcv_user = CloudCV_User.objects.all()
      serializer = CloudCV_UserSerializer(cloudcv_user, many=True)
      return Response(serializer.data)

  def post(self, request, format=None):
      serializer = CloudCV_UserSerializer(data=request.data)
      if serializer.is_valid():
          serializer.save()
          return Response(serializer.data, status=status.HTTP_201_CREATED)
      return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CloudCV_UserDetail(APIView):
  """
  Retrieve, update or delete a CloudCV_User instance.
  """
  def get_object(self, pk):
      try:
          return CloudCV_User.objects.get(pk=pk)
      except CloudCV_User.DoesNotExist:
          raise Http404

  def get(self, request, pk, format=None):
      cloudcv_user = self.get_object(pk)
      serializer = CloudCV_UserSerializer(cloudcv_user)
      return Response(serializer.data)

  def put(self, request, pk, format=None):
      cloudcv_user = self.get_object(pk)
      serializer = CloudCV_UserSerializer(cloudcv_user, data=request.data)
      if serializer.is_valid():
          serializer.save()
          return Response(serializer.data)
      return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

  def delete(self, request, pk, format=None):
      cloudcv_user = self.get_object(pk)
      cloudcv_user.delete()
      return Response(status=status.HTTP_204_NO_CONTENT)


# class RequestLogList(APIView):
#     """
#     List all the requst jobs and their respective details. 
#     """
#     def get(self, request, format=None):
#         jobs = RequestLog.objects.all()
#         serializer = RequestLogSerializer(jobs, many=True)
#         return Response(serializer.data)

#     def post(self, request, format=None):
#         serializer = RequestLogSerializer(data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=status.HTTP_201_CREATED)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# class GroupList(APIView):
#     """
#     List all the Groups, or create a new Group.
#     """
#     def get(self, request, format=None):
#         groups = Group.objects.all()
#         serializer = GroupSerializer(groups, many=True)
#         return Response(serializer.data)

#     def post(self, request, format=None):
#         serializer = GroupSerializer(data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=status.HTTP_201_CREATED)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

#     def post(self, request, format=None):
#         serializer = GroupSerializer(data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data, status=status.HTTP_201_CREATED)
#         return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# class GroupDetail(APIView):
#     """
#     Retrieve, update or delete a Group instance.
#     """
#     def get_object(self, pk):
#         try:
#             return Group.objects.get(pk=pk)
#         except Group.DoesNotExist:
#             raise Http404

#     def get(self, request, pk, format=None):
#         group = self.get_object(pk)
#         serializer = GroupSerializer(group)
#         return Response(serializer.data)

#     def put(self, request, pk, format=None):
#         group = self.get_object(pk)
#         serializer = GroupSerializer(group, data=request.data)
#         if serializer.is_valid():
#             serializer.save()
#             return Response(serializer.data)

#     def delete(self, request, pk, format=None):
#         group = self.get_object(pk)
#         group.delete()
#         return Response(status=status.HTTP_204_NO_CONTENT)

# class UserList(generics.ListCreateAPIView):
#     """
#     List all Users, or Create a new User
#     """
#     queryset = User.objects.all()
#     serializer_class = UserSerializer
#     model = User

# class UserDetail(generics.RetrieveUpdateDestroyAPIView):
#     """
#     Retrieve, Update or Delete a User instance
#     """
#     queryset = User.objects.all()
#     serializer_class = UserSerializer
#     model = User

# class RequestLogList(generics.ListCreateAPIView):
#     """
#     List all the request jobs and their respective details
#     """
#     queryset = RequestLog.objects.all()
#     serializer_class = RequestLogSerializer
#     model = RequestLog

# class RequestLogDetail(generics.RetrieveUpdateDestroyAPIView):
#     """
#     Retrieve, Update or Delete a Request
#     """
#     queryset = RequestLog.objects.all()
#     serializer_class = RequestLogSerializer
#     model = RequestLog

# class GroupList(generics.ListCreateAPIView):
#     """
#     List all Groups, or Create a new User
#     """    
#     queryset = Group.objects.all()
#     serializer_class = GroupSerializer
#     model = Group

# class GroupDetail(generics.RetrieveUpdateDestroyAPIView):
#     """
#     Retrieve, update or delete a Group instance
#     """
#     queryset = Group.objects.all()
#     serializer_class = GroupSerializer
#     model = Group

# class CurrentRequestList(generics.ListCreateAPIView):
#     """
#     List all the Current Request Jobs Running on CloudCV Server
#     """
#     queryset = CurrentRequest.objects.all()
#     serializer_class = CurrentRequestSerializer
#     model = CurrentRequest

# class CurrentRequestDetail(generics.RetrieveUpdateDestroyAPIView):
#     """
#     Retrieve, update or delete a current running Job Request instance
#     """
#     queryset = CurrentRequest.objects.all()
#     serializer_class = CurrentRequestSerializer
#     model = CurrentRequest

# class ImagesList(generics.ListCreateAPIView):
#     """
#     List all the images or add the Images  
#     """
#     queryset = Images.objects.all()
#     serializer_class = ImagesSerializer
#     model = Images

# class ImagesDetail(generics.RetrieveUpdateDestroyAPIView):
#     """
#     Retrieve, update or delete an Image instance
#     """
#     queryset = Images.objects.all()
#     serializer_class = ImagesSerializer
#     model = Images

# class ModelStorageList(generics.ListCreateAPIView):
#     """
#     List all the Models or add Models 
#     """
#     queryset = ModelStorage.objects.all()
#     serializer_class = ModelStorageSerializer
#     model = ModelStorage

# class ModelStorageDetail(generics.RetrieveUpdateDestroyAPIView):
#     """
#     Retrieve, update or delete an ModelStorage instance.
#     """
#     queryset = ModelStorage.objects.all()
#     serializer_class = ModelStorageSerializer
#     model = ModelStorage
# class ImagesDetail(generics.RetrieveUpdateDestroyAPIView):
#     """
#     Retrieve, update or delete an Image instance
#     """
#     queryset = Images.objects.all()
#     serializer_class = ImagesSerializer
#     model = Images

# class ModelStorageList(generics.ListCreateAPIView):
#     """
#     List all the Models or add Models 
#     """
#     queryset = ModelStorage.objects.all()
#     serializer_class = ModelStorageSerializer
#     model = ModelStorage
#     filter_fields = ('file_location','parameters', 'neural_network','database_used')

# class ModelStorageDetail(generics.RetrieveUpdateDestroyAPIView):
#     """
#     Retrieve, update or delete an ModelStorage instance.
#     """
#     queryset = ModelStorage.objects.all()
#     serializer_class = ModelStorageSerializer
#     model = ModelStorage

#############################################################

from django.contrib.auth.models import User
from allauth.socialaccount.models import * 
from cloudcv17 import *
from app.models import *
from dropbox.client import DropboxClient
from dropbox.session import DropboxSession
from boto.s3.connection import * 
from apiclient import errors
from apiclient.http import MediaFileUpload
from cloudcv17.settings import *
from os import path
import httplib2
import json
import traceback
import glob
import os
import dropbox

class UploadApiTest(TemplateView):
    def get(self, request, *args, **kwargs):
        providers = []
        tokens = SocialToken.objects.filter(account__user__id = request.user.id)
        for i in tokens:
            providers.append(str(i.app))
        s3 = StorageCredentials.objects.filter(user__id = request.user.id).count()
        if s3:
            providers.append("Amazon S3")
        return render_to_response("app/upload_to_storage.html",{'p':providers},context_instance = RequestContext(request))
    
    @csrf_exempt
    def post(self,request):
        print "POST Request to API "
        source_path = request.POST['source_path']
        path = request.POST['dest_path']
        if path.split("//")[0][:-1]=="s3":
            print "S3 is working "
            bucket = path.split("//")[1]
            dest_path = "/"+str(path.split("//")[2])
            result = put_data_on_s3(request,dest_path,bucket)
        else:
            if path.split("//")[0][:-1]=="dropbox":
                dest_path = path.split("//")[1]
                access_token = SocialToken.objects.get(account__user__id = request.user.id, app__name = "Dropbox")
                # print "ACCESS TOKEN: ",access_token
                session = DropboxSession(settings.DROPBOX_APP_KEY, settings.DROPBOX_APP_SECRET)
                access_key, access_secret = access_token.token, access_token.token_secret  # Previously obtained OAuth 1 credentials
                session.set_token(access_key, access_secret)
                client = DropboxClient(session)
                token = client.create_oauth2_access_token()
                result = put_data_on_dropbox(request, source_path, dest_path, token)
            elif str(storage)=="Google Drive":
                # try:
                print "############## GOOGLE DRIVE ##############   "
                storage = Storage(SocialToken, 'id', request.user.id, 'token')
                print storage
                credential = storage.get()
                # credentials = SocialToken.objects.get(account__user__id = request.user.id, app__name = storage)
                # credentials = credentials.token
                http = credential.authorize(httplib2.Http())
                service = discovery.build('drive', 'v2', http=http)
                results = service.files().list(maxResults=10).execute()
                items = results.get('items', [])
                if not items:
                    print 'No files found.'
                else:
                    print 'Files:'
                    for item in items:
                        print '{0} ({1})'.format(item['title'], item['id'])
                result = put_data_on_google_drive(request,path,access_token.token)
                # except:
                #   pass
        return HttpResponse(json.dumps(result), content_type="application/json")

def put_data_on_s3(request, source_path, dest_path,bucket):
    result = {}
    # source_path = request.POST['source_path']
    print "the source path is ", source_path
    # files = [ os.path.abspath(f) for f in os.listdir(source_path) if path.isfile(f)]
    files = [name for name in glob.glob(os.path.join(source_path,'*.*')) if os.path.isfile(os.path.join(source_path,name))]
    print files
    result['sourcePath'] = source_path
    result['dest_path'] = request.POST['dest_path']
    result['bucket'] = bucket
    # result['storage'] = request.POST['storageName']
    result['uplaodedTo']= []
    result['user'] = request.user.email
    s3 = StorageCredentials.objects.get(user__id = request.user.id)
    conn = S3Connection(s3.aws_access_key,s3.aws_access_secret)
    try:
        b = conn.get_bucket(bucket)
        print "TRY "
    except:
        print "CATCH"
        b = conn.create_bucket(bucket)
    for i in files:
        # upload_file_on_cloudcv_server(i)
        k = Key(b)
        k.key = dest_path+i.split("/")[-1]
        result['uplaodedTo'].append(k.key)
        k.set_contents_from_filename(i)
        print i
    return result


def put_data_on_dropbox(request, source_path, dest_path,access_token):
    result = {}
    client = dropbox.client.DropboxClient(access_token)
    result['pathProvided'] = dest_path
    result['user'] = request.user.email
    result['uplaodedTo'] = []
    files = [name for name in glob.glob(os.path.join(source_path,'*.*')) if os.path.isfile(os.path.join(source_path,name))]
    for i in files:
        f = open(i,'rb')
        response = client.put_file(dest_path+i.split("/")[-1], f)
        result['uplaodedTo'].append(response)
    return result



class DownloadApiTest(TemplateView):
    def get(self, request, *args, **kwargs):
        providers = []
        tokens = SocialToken.objects.filter(account__user__id = request.user.id)
        for i in tokens:
            providers.append(str(i.app))
        s3 = StorageCredentials.objects.filter(user__id = request.user.id).count()
        if s3:
            providers.append("Amazon S3")
        return render_to_response("app/download_from_storage.html",{'p':providers},context_instance = RequestContext(request))
    
    def post(self,request):
        path = request.POST['source_path']
        dest_path = request.POST['dest_path']
        print "POST Request to Download API "
        path = request.POST['source_path']
        if path.split("//")[0][:-1]=="s3":
            print "S3 is working "
            bucket = path.split("//")[1]
            source_path = "/"+str(path.split("//")[2])
            result = get_data_from_s3(request, source_path, dest_path, bucket)
        else:
            if path.split("//")[0][:-1]=="dropbox":
                access_token = SocialToken.objects.get(account__user__id = request.user.id, app__name = "Dropbox")
                # print "ACCESS TOKEN: ",access_token
                session = DropboxSession(settings.DROPBOX_APP_KEY, settings.DROPBOX_APP_SECRET)
                access_key, access_secret = access_token.token, access_token.token_secret  # Previously obtained OAuth 1 credentials
                session.set_token(access_key, access_secret)
                client = DropboxClient(session)
                token = client.create_oauth2_access_token()
                result = get_data_from_dropbox(request, source_path, dest_path, token)
            elif storage=="Google Drive":
                get_data_from_google(request,path,access_token)
        return HttpResponse(json.dumps(result), content_type="application/json")


def get_data_from_s3(request,source_path, dest_path, bucket):
    result = {}
    try:
        s3 = StorageCredentials.objects.get(user__id = request.user.id)
        conn = S3Connection(s3.aws_access_key,s3.aws_access_secret)
        b = conn.get_bucket(bucket)
        result['user'] = request.user.email
        result['bucket'] = bucket
        result['location']= []
        result['downloadTo'] = []
    except:
        result['error'] = "Check if the S3 bucket exists or not."
        return result
    bucket_entries = b.list(source_path[1:])
    if dest_path[-1]!="/":
        dast_path+="/"
    for i in bucket_entries:
        result['location'].append(i.key)
        file_name = str(i.key).split("/")[-1]
        result['downloadTo'].append(dest_path+file_name)
        i.get_contents_to_filename(dest_path+file_name)
    return result


up_storage_api = login_required(UploadApiTest.as_view())
down_storage_api = login_required(DownloadApiTest.as_view())

