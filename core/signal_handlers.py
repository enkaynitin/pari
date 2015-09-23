from HTMLParser import HTMLParser
import urllib
import urlparse

from django.db.models.signals import post_save, pre_delete
from django.conf import settings
from django.dispatch import receiver
from django.core import mail
from django.contrib.sites.models import Site
from django.template import loader, Context

from wagtail.wagtailembeds.models import Embed
from wagtail.wagtailsearch.signal_handlers import post_delete_signal_handler

from .models import AffixImage, AffixImageRendition, Page, Contact


@receiver(pre_delete, sender=AffixImage)
def image_delete(sender, instance, **kwargs):
    # Pass false so FileField doesn't save the model.
    instance.file.delete(False)


@receiver(pre_delete, sender=AffixImageRendition)
def rendition_delete(sender, instance, **kwargs):
    # Pass false so FileField doesn't save the model.
    instance.file.delete(False)


@receiver(post_save)
def create_translations_folder(sender, instance, **kwargs):
    if not isinstance(instance, Page):
        return None
    if instance.title == "Translations":
        post_delete_signal_handler(instance)
        return None
    if instance.get_ancestors().filter(title="Translations").count():
        return None
    # Currently allow translation on every page type
    if not instance.get_descendants().filter(title="Translations").count():
        instance.add_child(instance=Page(title="Translations", slug="translations"))


@receiver(post_save, sender=Contact)
def send_contact_mail(sender, instance, **kwargs):
    site = Site.objects.get_current()
    ctx = Context({
        "instance": instance,
        "site": site
    })
    get_tmpl = loader.get_template
    with mail.get_connection() as connection:
        subject = "Message from {0}".format(instance.name)
        body_html = get_tmpl("email/contact_us.html").render(ctx)
        body_txt = get_tmpl("email/contact_us.txt").render(ctx)
        msg = mail.EmailMultiAlternatives(
            subject, body_txt, settings.DEFAULT_FROM_EMAIL,
            settings.CONTACT_EMAIL_RECIPIENTS,
            reply_to=[instance.email], connection=connection)
        msg.attach_alternative(body_html, "text/html")
        msg.send()

        auto_reply_subject = "Acknowledgement from {0}".format(site.name)
        auto_reply_body_html = get_tmpl("email/auto_reply.html").render(ctx)
        auto_reply_body_txt = get_tmpl("email/auto_reply.txt").render(ctx)
        auto_reply = mail.EmailMultiAlternatives(
            auto_reply_subject, auto_reply_body_txt,
            settings.DEFAULT_FROM_EMAIL,
            [instance.email], connection=connection)
        auto_reply.attach_alternative(auto_reply_body_html, "text/html")
        auto_reply.send()


class YTIframeParser(HTMLParser):
    def handle_starttag(self, tag, attrs):
        tag_attr_dict = dict(attrs)
        parts = urlparse.urlsplit(tag_attr_dict["src"])
        url_attrs = dict(urlparse.parse_qsl(parts.query))
        url_attrs["showinfo"] = "0"
        url_attrs["rel"] = "0"
        url_attrs["modestbranding"] = "1"
        url_attrs["cc_load_policy"] = "1"
        url_attrs["autohide"] = "1"
        src_url = urlparse.urlunsplit((parts.scheme, parts.netloc,
                                       parts.path, urllib.urlencode(url_attrs),
                                       parts.fragment))
        tag_attr_dict["src"] = src_url
        attr_str = ""
        for (key, val) in tag_attr_dict.iteritems():
            attr_str += " {0}".format(key)
            if val:
                attr_str += "=\"{0}\"".format(val)
        self.yt_url = "<iframe{0}></iframe>".format(attr_str)


@receiver(post_save, sender=Embed)
def update_yt_params(sender, instance, **kwargs):
    if not kwargs["created"] or instance.provider_name.lower() != "youtube":
        return None
    ytp = YTIframeParser()
    ytp.feed(instance.html)
    instance.html = ytp.yt_url
    instance.save()
