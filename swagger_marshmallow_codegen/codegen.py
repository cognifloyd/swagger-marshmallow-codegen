# -*- coding:utf-8 -*-
import logging
from prestring.python import Module, LazyFormat
from dictknife import deepequal
from collections import defaultdict
from collections import OrderedDict
logger = logging.getLogger(__name__)


class Context(object):
    def __init__(self):
        self.m = Module()
        self.im = self.m.submodule()
        self.field_m = Module()


class Codegen(object):
    schema_class = "Schema"
    fields_module = "fields"

    def __init__(self, dispatcher, accessor):
        self.dispatcher = dispatcher
        self.accessor = accessor

    @property
    def resolver(self):
        return self.accessor.resolver

    def write_header(self, c):
        c.im.stmt("# -*- coding:utf-8 -*-")

    def write_import_(self, c):
        c.im.from_("marshmallow", "Schema")
        c.im.from_("marshmallow", "fields")

    def write_schema(self, c, d, clsname, definition, arrived):
        if clsname in arrived:
            return
        arrived.add(clsname)

        baseclass = self.schema_class

        if self.resolver.has_ref(definition):
            ref_name, ref_definition = self.resolver.resolve_ref_definition(d, definition)
            if ref_name is None:
                logger.info("ref: %r is not found", definition["$ref"])
                # error is raised?
            else:
                self.write_schema(c, d, ref_name, ref_definition, arrived)
                baseclass = ref_name

        with c.m.class_(clsname, baseclass):
            opts = defaultdict(OrderedDict)
            self.accessor.update_options_pre_properties(definition, opts)

            properties = self.accessor.properties(definition)
            if not properties:
                c.m.stmt("pass")
            else:
                for name, field in properties.items():
                    if self.resolver.has_many(field):
                        self.write_field_many(c, d, clsname, definition, name, field, opts[name])
                    else:
                        self.write_field_one(c, d, clsname, definition, name, field, opts[name])

    def write_body(self, c, d):
        arrived = set()
        for schema_name, definition in self.accessor.definitions(d).items():

            if not self.resolver.has_schema(definition):
                continue

            if self.resolver.has_many(definition):
                continue

            clsname = self.resolver.resolve_schema_name(schema_name)
            self.write_schema(c, d, clsname, definition, arrived)

    def write_field_one(self, c, d, schema_name, definition, name, field, opts):
        field_class_name = None
        if self.resolver.has_ref(field):
            field_class_name, field = self.resolver.resolve_ref_definition(d, field, level=1)
            if field_class_name == schema_name and deepequal(field, definition):
                field_class_name = "self"

            # finding original definition
            if self.resolver.has_ref(field):
                ref_name, field = self.resolver.resolve_ref_definition(d, field)
                if ref_name is None:
                    logger.info("ref: %r is not found", field["$ref"])
                    return

        self.accessor.update_option_on_property(field, opts)

        path = self.dispatcher.dispatch(self.accessor.type_and_format(name, field))
        if path is None:
            logger.info("path: matched path is not found. name=%r, schema=%r", name, schema_name)
            return

        module, field_name = path.rsplit(":", 1)
        # todo: import module
        if module == "marshmallow.fields":
            module = self.fields_module

        kwargs = ", ".join(("{}={}".format(k, repr(v)) for k, v in opts.items()))

        if self.resolver.has_schema(field) and field_class_name:
            if kwargs:
                kwargs = ", " + kwargs
            c.m.stmt(LazyFormat("{} = {}.{}({!r}{})", name, module, field_name, field_class_name, kwargs))
        else:
            # field
            c.m.stmt(LazyFormat("{} = {}.{}({})", name, module, field_name, kwargs))

    def write_field_many(self, c, d, schema_name, definition, field_name, field, opts):
        opts["many"] = True
        field = field["items"]
        return self.write_field_one(c, d, schema_name, definition, field_name, field, opts)

    def codegen(self, d, ctx=None):
        c = ctx or Context()
        self.write_header(c)
        c.m.sep()
        self.write_import_(c)
        self.write_body(c, d)
        return c.m
