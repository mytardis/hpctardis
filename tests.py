# -*- coding: utf-8 -*-
#
# Copyright (c) 2011-2011, RMIT e-Research Office
#   (RMIT University, Australia)
# Copyright (c) 2010-2011, Monash e-Research Centre
#   (Monash University, Australia)
# All rights reserved.
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
#    *  Redistributions of source code must retain the above copyright
#       notice, this list of conditions and the following disclaimer.
#    *  Redistributions in binary form must reproduce the above copyright
#       notice, this list of conditions and the following disclaimer in the
#       documentation and/or other materials provided with the distribution.
#    *  Neither the name of the VeRSI, the VeRSI Consortium members, nor the
#       names of its contributors may be used to endorse or promote products
#       derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE REGENTS AND CONTRIBUTORS ``AS IS'' AND ANY
# EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE REGENTS AND CONTRIBUTORS BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

"""
tests.py

.. moduleauthor:: Ian Thomas <Ian.Edward.Thomas@rmit.edu.au>

"""
import logging
import re
from os import path
   
from django.test import TestCase
from django.test.client import Client
from django.conf import settings

from tardis.tardis_portal import models
from tardis.tardis_portal.auth.localdb_auth import django_user

from tardis.apps.hpctardis.metadata import get_metadata
from tardis.apps.hpctardis.metadata import get_schema
from tardis.apps.hpctardis.metadata import save_metadata
from tardis.apps.hpctardis.metadata import go

from tardis.tardis_portal.ParameterSetManager import ParameterSetManager
from tardis.tardis_portal.models import ParameterName
from tardis.tardis_portal.models import ExperimentACL, Experiment, UserProfile
from tardis.tardis_portal.models import DatasetParameterSet
from tardis.tardis_portal.models import DatasetParameter
from tardis.tardis_portal.models import Schema

logger = logging.getLogger(__name__)

class SimpleTest(TestCase):
    def test_basic_addition(self):
        """
        Tests that 1 + 1 always equals 2.
        """
        self.assertEqual(1 + 1, 2)


def _grep(string, l):
    expr = re.compile(string)
    match = expr.search(l)
    return match

class SimplePublishTest(TestCase):
    """ Publish Experiments as RIFCS"""
    
    def setUp(self):
        self.client = Client()
        from django.contrib.auth.models import User
        self.username = 'tardis_user1'
        self.pwd = 'secret'
        email = ''
        self.user = User.objects.create_user(self.username, email, self.pwd)
        self.userprofile = UserProfile(user=self.user)
      
    def tearDown(self):
        from shutil import rmtree
        rmtree(self.experiment_path)
        
    def test_publish(self):
        """ Create an experiment and publish it as RIF-CS using RMITANDSService"""
        login = self.client.login(username=self.username,
                                  password=self.pwd)
        self.assertTrue(login)
        # Create simple experiment
        exp = models.Experiment(title='test exp1',
                                institution_name='rmit',
                                created_by=self.user,
                                public=True
                                )
        exp.save()
        acl = ExperimentACL(
            pluginId=django_user,
            entityId=str(self.user.id),
            experiment=exp,
            canRead=True,
            isOwner=True,
            aclOwnershipType=ExperimentACL.OWNER_OWNED,
            )
        acl.save()
        self.assertEqual(exp.title, 'test exp1')
        self.assertEqual(exp.url, None)
        self.assertEqual(exp.institution_name, 'rmit')
        self.assertEqual(exp.approved, False)
        self.assertEqual(exp.handle, None)
        self.assertEqual(exp.created_by, self.user)
        self.assertEqual(exp.public, True)
        self.assertEqual(exp.get_or_create_directory(),
                         path.join(settings.FILE_STORE_PATH, str(exp.id)))

        self.experiment_path = path.join(settings.FILE_STORE_PATH, str(exp.id))
        # publish
        data = {'legal':'on',
                'profile':'default.xml'}
        response = self.client.post("/apps/hpctardis/publisher/1/", data)
        
        logger.debug("response=%s" % response)
        # check resulting rif-cs
        response = self.client.post("/apps/hpctardis/rif_cs/")
        self.assertTrue(_grep("test exp1",str(response)))
        self.assertTrue(_grep("<key>http://www.rmit.edu.au/HPC/1</key>",str(response)))
        self.assertTrue(_grep("""<addressPart type="text">rmit</addressPart>""",str(response)))
        self.assertFalse(_grep("<key>http://www.rmit.edu.au/HPC/2</key>",str(response)))
        logger.debug("response=%s" % response)
        
        
class VASPMetadataTest(TestCase):
    """ Tests ability to create experiments, dataset with VASP datafiles and extract appropriate datafiles"""
    
    def setUp(self):
        self.client = Client()
        from django.contrib.auth.models import User
        self.username = 'tardis_user1'
        self.pwd = 'secret'
        email = ''
        self.user = User.objects.create_user(self.username, email, self.pwd)
        self.userprofile = UserProfile(user=self.user)
    
    
    def tearDown(self):
        from shutil import rmtree
        rmtree(self.experiment_path)
          
    def _test_metadata(self,schema,name,dataset,fields):
        """ Check that metadata is correct"""
        try:
            sch = models.Schema.objects.get(namespace__exact=schema,name=name)
        except Schema.DoesNotExist:
            self.assertTrue(False)
        self.assertEqual(schema,sch.namespace)
        self.assertEqual(name,sch.name)
        try:
            datasetparameterset = models.DatasetParameterSet.objects.get(schema=sch, dataset=dataset)
        except DatasetParameterSet.DoesNotExist:
            self.assertTrue(False) 
        psm = ParameterSetManager(parameterset=datasetparameterset)
        for key, field_type, value in fields:
            logger.debug("key=%s,field_type=%s,value=%s" % (key,field_type, value))
            try:
                # First check stringed value
                param = psm.get_param(key,value=True)
                self.assertEquals(str(param),str(value))
                # Then correct type
                param = psm.get_param(key,value=False)
                self.assertEquals(param.name.data_type,field_type)
            except DatasetParameter.DoesNotExist:
                logger.error("cannot find %s" % key)
                self.assertTrue(False)
                
    def _metadata_extract(self,expname,files,ns,schname,results):
        """ Check that we can create an VASP experiment and extract metadata from it"""
        
        login = self.client.login(username=self.username,
                                  password=self.pwd)
        self.assertTrue(login)
        exp = models.Experiment(title=expname,
                                institution_name='rmit',
                                created_by=self.user,
                                public=True
                                )
        exp.save()
        acl = ExperimentACL(
            pluginId=django_user,
            entityId=str(self.user.id),
            experiment=exp,
            canRead=True,
            isOwner=True,
            aclOwnershipType=ExperimentACL.OWNER_OWNED,
            )
        acl.save()
        self.assertEqual(exp.title, expname)
        self.assertEqual(exp.url, None)
        self.assertEqual(exp.institution_name, 'rmit')
        self.assertEqual(exp.approved, False)
        self.assertEqual(exp.handle, None)
        self.assertEqual(exp.created_by, self.user)
        self.assertEqual(exp.public, True)
        self.assertEqual(exp.get_or_create_directory(),
                         path.join(settings.FILE_STORE_PATH, str(exp.id)))

        self.experiment_path = path.join(settings.FILE_STORE_PATH, str(exp.id))
      
        dataset = models.Dataset(description="dataset description...",
                                 experiment=exp)
        dataset.save()
        for f in files:
            self._make_datafile(dataset,
                       path.join(path.abspath(path.dirname(__file__)),f))       
        go()
        self._test_metadata(ns,schname,dataset,results)
                
    def test_metadata1(self):
        """ Test first set of VASP data"""
        self._metadata_extract(expname="testexp1",
                                 files = ['testing/dataset1/OUTCAR',
                                          'testing/dataset1/KPOINTS',
                                          'testing/dataset1/vasp.sub.o813344',
                                          'testing/dataset1/INCAR',
                                          'testing/dataset1/POSCAR' ],
                               ns="http://tardis.edu.au/schemas/vasp/1",
                               schname="vasp 1.0",
                               results= [("kpoint_grid",ParameterName.STRING," 8  8  8   \n"),
                                        ("kpoint_grid_offset",ParameterName.STRING," 0  0  0\n"),
                                          ("ENCUT",ParameterName.NUMERIC,"400.0"),
                                          ("NIONS",ParameterName.NUMERIC,"216.0"),
                                          ("NELECT",ParameterName.NUMERIC,"864.0"),
                                          ("ISIF",ParameterName.NUMERIC,"3.0"),
                                          ("ISPIN",ParameterName.NUMERIC,"4.0"),
                                          ("Walltime",ParameterName.STRING,"01:59:17"),
                                          ("Number Of CPUs",ParameterName.NUMERIC,"64.0"),
                                          ("Maximum virtual memory",ParameterName.NUMERIC,"27047.0"),
                                          ("Max jobfs disk use",ParameterName.NUMERIC,"0.1"),
                                          ("NSW",ParameterName.NUMERIC,"42.0"),
                                          ("IBRION",ParameterName.NUMERIC,"2.0"),
                                          ("ISMEAR",ParameterName.NUMERIC,"-6.0"),
                                          ("POTIM",ParameterName.NUMERIC,"0.5"),
                                          ("MAGMOM",ParameterName.STRING,"   1.00000000000000     \n\n    10.6863390000000003    0.0000000000000000    0.0000000000000000\n\n     0.0000000000000000   10.6863390000000003    0.0000000000000000\n"),
                                          ("EDIFF",ParameterName.NUMERIC,"0.0001"),
                                          ("EDIFFG",ParameterName.NUMERIC,"0.001"),
                                          ("NELM",ParameterName.NUMERIC,"60.0")
                                                                         ])
        
    def test_metadata2(self):
        """ Tests second set of VASP data"""
        
        self._metadata_extract(expname="testexp2",
                                 files = ['testing/dataset2/OUTCAR',
                                          'testing/dataset2/KPOINTS',
                                          'testing/dataset2/vasp.sub.o935843',
                                          'testing/dataset2/INCAR',
                                          'testing/dataset2/POSCAR' ],
                               ns="http://tardis.edu.au/schemas/vasp/1",
                               schname="vasp 1.0",
                               results= [("kpoint_grid",ParameterName.STRING," 8  8  8   \n"),
                                        ("kpoint_grid_offset",ParameterName.STRING," 0  0  0\n"),
                                          ("ENCUT",ParameterName.NUMERIC,"400.0"),
                                          ("NIONS",ParameterName.NUMERIC,"215.0"),
                                          ("NELECT",ParameterName.NUMERIC,"800.0"),
                                          ("ISIF",ParameterName.NUMERIC,"2.0"),
                                          ("ISPIN",ParameterName.NUMERIC,"1.0"),
                                          ("Walltime",ParameterName.STRING,"04:27:18"),
                                          ("Number Of CPUs",ParameterName.NUMERIC,"56.0"),
                                          ("Maximum virtual memory",ParameterName.NUMERIC,"57537.0"),
                                          ("Max jobfs disk use",ParameterName.NUMERIC,"0.1"),
                                          ("NSW",ParameterName.NUMERIC,"0.0"),
                                          ("IBRION",ParameterName.NUMERIC,"-1.0"),
                                          ("ISMEAR",ParameterName.NUMERIC,"-99.0"),
                                          ("POTIM",ParameterName.NUMERIC,"0.5"),
                                          ("MAGMOM",ParameterName.STRING,"   1.00000000000000     \n\n    10.6851970403940548    0.0000000000000000    0.0000000000000000\n\n     0.0000000000000000   10.6851970403940548    0.0000000000000000\n"),
                                          ("EDIFF",ParameterName.NUMERIC,"5e-06"),
                                          ("EDIFFG",ParameterName.NUMERIC,"5e-05"),
                                          ("NELM",ParameterName.NUMERIC,"60.0")
                                                                         ])
        
    def _make_datafile(self,dataset,filename):
        """ Make datafile from filename in given dataset"""
 
        df_file = models.Dataset_File(dataset=dataset,
                                      filename=path.basename(filename),
                                      url=filename,
                                      protocol='staging')
        df_file.save()
        return df_file
 
        
        
        
    
      