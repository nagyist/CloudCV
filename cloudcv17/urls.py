from django.conf.urls import patterns, include, url
from django.contrib import admin

import os
admin.autodiscover()

urlpatterns = patterns('',
    (r'^', include('allauth.urls')),
    url(r'^', include('app.urls')),
    url(r'^upload/', include('app.urls')),
    # Uncomment the admin/doc line below to enable admin documentation:
    # url(r'^admin/doc/', include('django.contrib.admindocs.urls')),
    url(r'^admin/', include(admin.site.urls)),
)

urlpatterns += patterns('',
                        (r'^media/(.*)$', 'django.views.static.serve',
                         {'document_root': os.path.join(os.path.abspath(os.path.dirname(__file__)), 'media')}),
                        )
