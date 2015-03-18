# -*- coding: utf-8 -*-

from collective.documentgenerator.testing import EXAMPLE_POD_TEMPLATE_INTEGRATION

from plone import api

from zope.component import queryUtility
from zope.schema.interfaces import IVocabularyFactory

import unittest


class TestVocabularies(unittest.TestCase):

    layer = EXAMPLE_POD_TEMPLATE_INTEGRATION

    def setUp(self):
        self.portal = self.layer['portal']
        self.registry = api.portal.get_tool('portal_registry')

    def test_portal_type_vocabulary_factory_registration(self):
        """
        Portal type voc factory should be registered as a named utility.
        """
        factory_name = 'collective.documentgenerator.PortalType'
        self.assertTrue(queryUtility(IVocabularyFactory, factory_name))

    def test_portal_type_vocabulary_values(self):
        """
        Test some Portal_type values.
        """
        voc_name = 'collective.documentgenerator.PortalType'
        vocabulary = queryUtility(IVocabularyFactory, voc_name)
        permissions_voc = vocabulary(self.portal)
        self.assertTrue('Plone Site' in permissions_voc)
        self.assertTrue('Event' in permissions_voc)

    def test_style_vocabulary_factory_registration(self):
        """
        Styles voc factory should be registered as a named utility.
        """
        factory_name = 'collective.documentgenerator.StyleTemplates'
        self.assertTrue(queryUtility(IVocabularyFactory, factory_name))

    def test_style_vocabulary_values(self):
        """
        Test some style values.
        """
        voc_name = 'collective.documentgenerator.StyleTemplates'
        vocabulary = queryUtility(IVocabularyFactory, voc_name)
        style_voc = vocabulary(self.portal)
        style_template = self.portal.podtemplates.test_style_template
        self.assertTrue(style_template.UID() in style_voc)

    def test_merge_templates_vocabulary_factory_registration(self):
        """
        Merge templates voc factory should be registered as a named utility.
        """
        factory_name = 'collective.documentgenerator.MergeTemplates'
        self.assertTrue(queryUtility(IVocabularyFactory, factory_name))
