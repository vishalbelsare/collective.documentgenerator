# -*- coding: utf-8 -*-
import copy
import logging

from Products.CMFCore.interfaces import IDublinCore
from Products.CMFPlone.utils import safe_unicode
from collective.documentgenerator import _
from collective.documentgenerator.config import NEUTRAL_FORMATS
from collective.documentgenerator.config import ODS_FORMATS
from collective.documentgenerator.config import ODT_FORMATS
from collective.documentgenerator.config import POD_FORMATS
from collective.documentgenerator.content.style_template import StyleTemplate
from collective.documentgenerator.interfaces import IPODTemplateCondition
from collective.documentgenerator.interfaces import ITemplatesToMerge
from collective.documentgenerator.utils import compute_md5
from collective.z3cform.datagridfield import DataGridFieldFactory
from collective.z3cform.datagridfield import DictRow
from imio.helpers.content import add_to_annotation, del_from_annotation, get_from_annotation
from plone import api
from plone.autoform import directives as form
from plone.autoform.interfaces import IFormFieldProvider
from plone.dexterity.content import Item
from plone.formwidget.namedfile import NamedFileWidget
from plone.namedfile.field import NamedBlobFile
from plone.supermodel import model
from z3c.form import validator
from z3c.form.browser.checkbox import CheckBoxFieldWidget
from z3c.form.browser.checkbox import SingleCheckBoxFieldWidget
from z3c.form.browser.orderedselect import OrderedSelectFieldWidget
from z3c.form.browser.radio import RadioFieldWidget
from z3c.form.browser.select import SelectWidget
from zope import schema
from zope.component import provideAdapter, adapter
from zope.component import queryAdapter
from zope.component import queryMultiAdapter
from zope.interface import Interface, provider, implementer
from zope.interface import Invalid
from zope.interface import implements
from zope.interface import invariant

logger = logging.getLogger('collective.documentgenerator: PODTemplate')


class IPODTemplate(model.Schema):
    """
    PODTemplate dexterity schema.
    """

    model.primary('odt_file')
    form.widget('odt_file', NamedFileWidget)
    odt_file = NamedBlobFile(
        title=_(u'ODT File'),
        required=False,
    )

    form.omitted('initial_md5')
    initial_md5 = schema.TextLine(description=u'Initially loaded file md5. Will be compared with os file md5.')

    form.omitted('style_modification_md5')
    style_modification_md5 = schema.TextLine(description=u'Working md5, stored when styles only update.')

    form.widget('enabled', RadioFieldWidget)
    enabled = schema.Bool(
        title=_(u'Enabled'),
        default=True,
        required=False,
    )


class PODTemplate(Item):
    """
    PODTemplate dexterity class.
    """

    implements(IPODTemplate)

    def can_be_generated(self, context):
        """
        Evaluate if the template can be generated on a given context.
        """
        condition_obj = queryMultiAdapter((self, context), IPODTemplateCondition)
        if condition_obj:
            can_be_generated = condition_obj.evaluate()
            return can_be_generated

    def get_style_template(self):
        """
        Return associated StylesTemplate from which styles will be imported
        to the current PODTemplate.
        """
        return None

    def get_templates_to_merge(self):
        """
        Return associated PODTemplates merged into the current PODTemplate
        when it is rendered.
        """
        templates_to_merge = queryAdapter(self, ITemplatesToMerge)
        if templates_to_merge:
            return templates_to_merge.get()
        return {}

    def get_available_formats(self):
        """
        Returns formats in which current template may be generated.
        """
        return ['odt', ]

    @property
    def current_md5(self):
        md5 = u''
        if self.odt_file:
            md5 = safe_unicode(compute_md5(self.odt_file.data))
        return md5

    def has_been_modified(self):
        """
            Current md5 will also be different from initial_md5 without user modification but if style modification.
            Current_md5 will be equal to style_modification_md5 if style only update.
            This last one will be updated after style modification only. See events
        """
        return self.current_md5 != self.style_modification_md5

    def get_optimize_tables(self):
        """By default, return -1 meaning use global config value."""
        return -1

    def add_parent_pod_annotation(self):
        return None

    def del_parent_pod_annotation(self):
        return None

    def has_linked_template(self):
        return False


class IMergeTemplatesRowSchema(Interface):
    """
    Schema for DataGridField widget's row of field 'merge_templates'
    """
    template = schema.Choice(
        title=_(u'Template'),
        vocabulary='collective.documentgenerator.MergeTemplates',
        required=True,
    )

    pod_context_name = schema.TextLine(
        title=_(u'POD context name'),
        required=True,
    )

    form.widget('do_rendering', RadioFieldWidget)
    do_rendering = schema.Bool(
        title=_(u'Do rendering'),
    )


class IContextVariablesRowSchema(Interface):
    """
    Schema for DataGridField widget's row of field 'context_variables'
    """
    name = schema.TextLine(
        title=_(u'Variable name'),
        required=True,
    )

    value = schema.TextLine(
        title=_(u'Value'),
        required=False,
    )


class PodFormatsValidator(validator.SimpleFieldValidator):
    """ z3c.form validator class for Pod formats """

    def validate(self, value, force=False):
        # thanks to widget, we get just-loaded file.filename.
        widgets = self.view.widgets
        current_filename = u""
        for element in widgets.items():
            if element[0] == 'odt_file':
                current_filename = safe_unicode(element[1].filename)
        if current_filename:
            FORMATS_DICT = {'ods': ODS_FORMATS + NEUTRAL_FORMATS,
                            'odt': ODT_FORMATS + NEUTRAL_FORMATS}
            extension = current_filename.split('.')[-1]
            authorise_element_list = FORMATS_DICT[extension]
            authorise_extension_list = [elem[0] for elem in authorise_element_list]
            if not value:
                raise Invalid(_(u"No format selected"))
            for element in value:
                if element not in authorise_extension_list:
                    elem = self.get_invalid_error(element)
                    error_message = _(
                        u"element_not_valid",
                        default=u"Element ${elem} is not valid for .${extension} template : \"${template}\"",
                        mapping={u"elem": elem, u"extension": extension, u"template": current_filename})
                    raise Invalid(error_message)

    def get_invalid_error(self, extension):
        for element in POD_FORMATS:
            if element[0] == extension:
                return element[1]


@provider(IFormFieldProvider)
class IConfigurablePODTemplate(IPODTemplate):
    """
    ConfigurablePODTemplate dexterity schema.
    """

    form.order_before(reusable='enabled')
    form.widget('reusable', SingleCheckBoxFieldWidget)
    reusable = schema.List(
        title=_(u'Reusable'),
        description=_(u'Check if this POD Template can be reused by other POD Template'),
        required=False,
    )

    form.order_before(pod_template_to_use='enabled')
    pod_template_to_use = schema.Choice(
        title=_(u'Select Existing POD Template'),
        description=_(u'Choose an existing PDO template to use for this template.'),
        vocabulary='collective.documentgenerator.ExistingPODTemplate',
        required=False,
    )

    form.widget('pod_formats', OrderedSelectFieldWidget, multiple='multiple', size=5)
    pod_formats = schema.List(
        title=_(u'Available formats'),
        description=_(u'Select format in which the template will be generable.'),
        value_type=schema.Choice(source='collective.documentgenerator.Formats'),
        required=True,
        default=['odt', ],
    )

    form.widget('pod_portal_types', CheckBoxFieldWidget, multiple='multiple', size=15)
    pod_portal_types = schema.List(
        title=_(u'Allowed portal types'),
        description=_(u'Select for which content types the template will be available.'),
        value_type=schema.Choice(source='collective.documentgenerator.PortalTypes'),
        required=False,
    )

    form.widget('style_template', SelectWidget)
    style_template = schema.List(
        title=_(u'Style template'),
        description=_(u'Choose the style template to apply for this template.'),
        value_type=schema.Choice(source='collective.documentgenerator.StyleTemplates'),
        required=True,
    )

    form.widget('merge_templates', DataGridFieldFactory)
    merge_templates = schema.List(
        title=_(u'Templates to merge.'),
        required=False,
        value_type=DictRow(
            schema=IMergeTemplatesRowSchema,
            required=False
        ),
        default=[],
    )

    form.widget('context_variables', DataGridFieldFactory)
    context_variables = schema.List(
        title=_(u'Context variables.'),
        description=_("These context variables are added to the odt_file context."),
        required=False,
        value_type=DictRow(
            schema=IContextVariablesRowSchema,
            required=False
        ),
    )

    mailing_loop_template = schema.Choice(
        title=_(u'Mailing loop template'),
        description=_(u'Choose the mailing loop template to apply for this template.'),
        vocabulary='collective.documentgenerator.EnabledMailingLoopTemplates',
        required=False,
    )

    optimize_tables = schema.Choice(
        title=_(u'Optimize tables'),
        description=_(u'This will apply the "Optimize table columns width" of '
                      u'LibreOffice to tables that do not use the '
                      u'"table-layout: fixed" CSS style.  If you do not select '
                      u'a value, the value from the global configuration will be used.'),
        vocabulary='collective.documentgenerator.OptimizeTables',
        required=True,
        default=-1
    )

    @invariant
    def validate_context_variables(data):
        keys = []
        forbidden = ['context', 'view', 'uids', 'brains', 'self']
        to_check = copy.deepcopy(data.context_variables or [])
        to_check.extend(copy.deepcopy(data.merge_templates or []))

        for line in to_check:
            value = ('name' in line and line['name']) or ('pod_context_name' in line and line['pod_context_name'])

            if value in forbidden:
                raise Invalid(_("You can't use one of these words: ${list}", mapping={'list': ', '.join(forbidden)}))

            if value in keys:
                raise Invalid(_("You have twice used the same name '${name}'", mapping={'name': value}))
            else:
                keys.append(value)

    @invariant
    def validate_pod_file(data):
        if not (data.odt_file or data.pod_template_to_use):
            raise Invalid(_("You must select an odt file or an existing pod template"), schema)

    @invariant
    def validate_pod_template_to_use(data):
        if data.pod_template_to_use and (data.reusable or data.odt_file):
            raise Invalid(_(
                "You can't select a POD Template or set this template reusable if you have chosen an existing POD Template."),
                schema)


# Set conditions for which fields the validator class applies
validator.WidgetValidatorDiscriminators(PodFormatsValidator, field=IConfigurablePODTemplate['pod_formats'])

# Register the validator so it will be looked up by z3c.form machinery
provideAdapter(PodFormatsValidator)


@implementer(IConfigurablePODTemplate)
@adapter(IDublinCore)
class ConfigurablePODTemplate(PODTemplate):
    """
    ConfigurablePODTemplate dexterity class.
    """

    implements(IConfigurablePODTemplate)

    parent_pod_annotation_key = 'linked_child_templates'

    def __setattr__(self, key, value):
        # do not attempt to register annotation if object not created yet.
        # object has no id until fully created
        if self.id and key == 'pod_template_to_use':
            if self.pod_template_to_use != value:
                if self.pod_template_to_use:
                    self.del_parent_pod_annotation()
                super(ConfigurablePODTemplate, self).__setattr__(key, value)
                self.add_parent_pod_annotation()
        else:
            super(ConfigurablePODTemplate, self).__setattr__(key, value)

    def __getattr__(self, key):
        value = super(ConfigurablePODTemplate, self).__getattr__(key)

        if key == 'odt_file' and not value and self.pod_template_to_use:
            value = api.content.get(UID=self.pod_template_to_use).odt_file

        return value

    def has_linked_template(self):
        return self.pod_template_to_use is not None

    def get_style_template(self):
        """
        Return associated StylesTemplate from which styles will be imported
        to the current PODTemplate.
        """
        catalog = api.portal.get_tool('portal_catalog')
        style_template_UID = self.style_template
        if not style_template_UID:
            # do not query catalog if no style_template
            return

        style_template_brain = catalog(UID=style_template_UID)

        if style_template_brain:
            style_template = style_template_brain[0].getObject()
        else:
            style_template = None

        return style_template

    def set_merge_templates(self, pod_template, pod_context_name, do_rendering=True, position=-1):
        old_value = list(self.merge_templates)
        newline = {'template': pod_template.UID(), 'pod_context_name': pod_context_name, 'do_rendering': do_rendering}
        if position >= 0:
            old_value.insert(position, newline)
        else:
            old_value.append(newline)
        self.merge_templates = old_value

    def get_templates_to_merge(self):
        """
        Return associated PODTemplates merged into the current PODTemplate
        when it is rendered.
        """
        catalog = api.portal.get_tool('portal_catalog')
        pod_context = {}

        if self.merge_templates:
            for line in self.merge_templates:
                pod_template = catalog(UID=line['template'])[0].getObject()
                pod_context[line['pod_context_name'].encode('utf-8')] = (pod_template, line['do_rendering'])

        return pod_context

    def get_available_formats(self):
        """
        Returns formats in which current template may be generated.
        """
        return self.pod_formats

    def get_context_variables(self):
        """
            Returns context_variables as dict
        """
        ret = {}
        for line in self.context_variables or []:
            # Simple boolean conversion actually implemented
            # May be improved with ZPublisher.Converters, managing boolean, int, date, string, text, ...
            # Those last values in a list box with string as default value
            val = line['value']
            if val == 'True':
                val = True
            elif val == 'False':
                val = False
            ret[line['name']] = val
        return ret

    def get_optimize_tables(self):
        return self.optimize_tables

    def add_parent_pod_annotation(self):
        if self.pod_template_to_use:
            add_to_annotation(ConfigurablePODTemplate.parent_pod_annotation_key, self.UID(),
                              uid=self.pod_template_to_use)

    def del_parent_pod_annotation(self):
        if hasattr(self, 'pod_template_to_use') and self.pod_template_to_use:
            del_from_annotation(ConfigurablePODTemplate.parent_pod_annotation_key, self.UID(),
                                uid=self.pod_template_to_use)

    def get_children_pod_template(self):
        """
        @see plone.api.content.get
        @see imio.helpers.content.get_from_annotation
        @see imio.helpers.content.del_from_annotation
        :return: a list containing the children templates.

        Handles the case when the uid doesn't match any object by deleting the uid from anotation.
        """
        res = []
        annotated = get_from_annotation(ConfigurablePODTemplate.parent_pod_annotation_key, self)
        if annotated:
            for uid in annotated:
                child = api.content.get(UID=uid)
                if child:
                    res.append(child)
                else:
                    # child doesn't exist anymore. api.content.get returned None
                    del_from_annotation(ConfigurablePODTemplate.parent_pod_annotation_key, uid, obj=self)
        return res


class ISubTemplate(IPODTemplate):
    """
    PODTemplate used only a sub template to merge
    """


class SubTemplate(PODTemplate):
    """
    PODTemplate used only a sub template to merge
    """

    implements(ISubTemplate)


class IMailingLoopTemplate(IPODTemplate):
    """
    PODTemplate used only to loop for mailing
    """


class MailingLoopTemplate(PODTemplate):
    """
    PODTemplate used only to loop for mailing
    """

    implements(IMailingLoopTemplate)


POD_TEMPLATE_TYPES = {
    PODTemplate.__name__: PODTemplate,
    ConfigurablePODTemplate.__name__: ConfigurablePODTemplate,
    SubTemplate.__name__: SubTemplate,
    MailingLoopTemplate.__name__: MailingLoopTemplate,
    StyleTemplate.__name__: StyleTemplate,
}
