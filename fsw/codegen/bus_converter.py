"""The F´ build's CDH component, `Cdh.BusConverter`, generated from its FPP declaration.

`Cdh.BusConverter` in `fsw/fpp/interfaces/Cdh.fpp` pairs each sensor role, as its annotation
states: a bus-typed input `<role>In` and an output `<role>Out` of the GNC's struct. `roles` reads
the pairs, and `render` emits the component's C++: per role, a conversion `convert_<role>`, inline
in the header, building the GNC struct from the bus struct by `fsw.codegen.fields.plan`, the rule
the Python build's converter follows, and a handler sending its result on `<role>Out`. A field must
be a one-dimensional array of a numeric primitive; anything else, a scalar among it, raises when
the code is generated.

It also emits the lab's test pins, `BusConverterPins.hpp`, which `_wise_fsw`'s module includes
once: `bus_<Struct>(<member>=...)` returns F´'s serialization of a bus struct built from its
members' values, one pin per bus struct a role takes, in the same domain as the bus emulator; and
`cdh_<role>(bus_bytes)` returns F´'s serialization of `convert_<role>`'s result for the bus struct
F´ deserializes from the bytes. The pins need no instance of the component: F´ builds with direct
port calls, so a port exists only in a topology, and the conversion is inline.

`python -m fsw.codegen.bus_converter <directory>` writes the three files into the directory from
the contract, `fsw.codegen.deployment.contract_files()`; CMake runs it during `just fsw`, into the
build directory.
"""

import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from fsw.codegen.deployment import contract_files
from fsw.codegen.fields import DTYPES, form, plan
from fsw.codegen.fpp_model import Model, Port, read

__all__ = ["Role", "main", "render", "roles"]

_CONVERTER = "Cdh.BusConverter"
"""The component whose port pairs are the roles."""

_REPOSITORY = Path(__file__).resolve().parents[2]

_PRIMITIVES = ("F32", "F64", "I8", "I16", "I32", "I64", "U8", "U16", "U32", "U64")
"""The element types the component copies and a bus pin takes, each in a one-dimensional array: the
numeric primitives, as the bus emulator's. F´ serializes `bool` unlike Python, so none takes it. A
scalar member is refused until a struct has one, so its first use adds its code with a compiled
test."""

_NUMBERS = [DTYPES[primitive] for primitive in _PRIMITIVES]
"""`_PRIMITIVES` as `fsw.codegen.fields.form` gives their element types."""


class Role(NamedTuple):
    """A sensor role's pair of `Cdh.BusConverter` ports.

    Attributes:
        role: the role, such as `imu`.
        bus: the bus struct's qualified FPP name, such as `Bus.ImuSensorMsg`.
        icd: the GNC struct's qualified FPP name, such as `Gnc.ImuReading`.
        input: the input port's name, `<role>In`.
        output: the output port's name, `<role>Out`.
    """

    role: str
    bus: str
    icd: str
    input: str
    output: str


def _carried(port: Port) -> str:
    """The struct a port carries: its one argument's type.

    Args:
        port: the port.

    Returns:
        The struct's qualified name.
    """
    [argument] = port.args
    return argument.type


def roles(model: Model) -> list[Role]:
    """Every role of `Cdh.BusConverter`: each bus-typed input, with its output.

    Args:
        model: the model holding the converter.

    Returns:
        The roles, in the converter's port order.

    Raises:
        ValueError: a role has no `<role>Out`, or a bus-typed one, naming the role.
    """
    converter = model.components[_CONVERTER]
    outputs = {port.name: port for port in converter.outputs}
    found = []
    for port in converter.inputs:
        bus = _carried(port)
        if not bus.startswith("Bus."):
            continue
        role = port.name.removesuffix("In")
        output = outputs.get(f"{role}Out")
        if output is None or _carried(output).startswith("Bus."):
            raise ValueError(
                f"{_CONVERTER}'s role {role} takes {bus} at {port.name} but has no {role}Out of a"
                " GNC type"
            )
        found.append(Role(role, bus, _carried(output), port.name, output.name))
    return found


def _cpp(name: str) -> str:
    """A qualified FPP name as C++ names it.

    Args:
        name: such as `Bus.ImuSensorMsg`.

    Returns:
        Such as `Bus::ImuSensorMsg`.
    """
    return name.replace(".", "::")


def _copies(model: Model, role: Role) -> list[str]:
    """The statements filling the role's GNC struct `icd` from its bus struct `bus`.

    Args:
        model: the model.
        role: the role.

    Returns:
        A statement per field, copying its array element by element.

    Raises:
        ValueError: a field breaks `fsw.codegen.fields.plan`'s rule, or is not a one-dimensional
            array of one of `_PRIMITIVES`, naming it.
    """
    bus, icd = model.types[role.bus], model.types[role.icd]
    sources = {m.name.lower(): (m.name, form(m, model.types)) for m in bus.members}
    statements = []
    for member, name, (shape, element) in plan(icd, model.types, sources, role.bus):
        if len(shape) != 1 or element not in _NUMBERS:
            raise ValueError(
                f"{role.icd}.{member.name} is {shape} {element}, which the F´ CDH does not copy:"
                " it copies one-dimensional arrays of the numeric primitives"
            )
        statements.append(
            f"        for (FwSizeType i = 0; i < {shape[0]}; i++) {{\n"
            f"            icd.get_{member.name}()[i] = bus.get_{name}()[i];\n"
            "        }"
        )
    return statements


_HEADER = """\
// Generated by fsw.codegen.bus_converter from {component}; never committed.
#ifndef CDH_BUSCONVERTER_HPP
#define CDH_BUSCONVERTER_HPP

#include "{base}"

namespace Cdh {{

class BusConverter final : public BusConverterComponentBase {{
  public:
    explicit BusConverter(const char* compName);
{conversions}
  private:
{declarations}
}};

}}  // namespace Cdh

#endif
"""

_SOURCE = """\
// Generated by fsw.codegen.bus_converter from {component}; never committed.
#include "BusConverter.hpp"

namespace Cdh {{

BusConverter::BusConverter(const char* compName) : BusConverterComponentBase(compName) {{}}
{definitions}
}}  // namespace Cdh
"""

_CONVERSION = """
    //! Role {role}'s GNC struct from its bus struct.
    static {icd} convert_{role}(const {bus}& bus) {{
        {icd} icd;
{copies}
        return icd;
    }}
"""

_HANDLER = """
void BusConverter::{signature} {{
    this->{output}_out(0, convert_{role}(msg));
}}
"""

_PINS = """\
// Generated by fsw.codegen.bus_converter from {component}; never committed.
// The lab's test pins on the CDH component and the bus structs, compiled into _wise_fsw's module:
// its source includes this header once and calls busConverterPins(m) once.
#ifndef CDH_BUSCONVERTERPINS_HPP
#define CDH_BUSCONVERTERPINS_HPP

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <array>
#include <stdexcept>
#include <string>
#include <vector>

#include "BusConverter.hpp"

namespace {{

//! A struct's F´ serialization; raises naming the struct when F´ refuses it.
template <typename T>
pybind11::bytes busConverterSerialized(const T& value, const char* name) {{
    U8 data[T::SERIALIZED_SIZE];
    Fw::ExternalSerializeBuffer buffer(data, sizeof data);
    const Fw::SerializeStatus status = value.serializeTo(buffer);
    if (status != Fw::FW_SERIALIZE_OK) {{
        throw std::runtime_error(std::string(name) + ": F´ serialization failed with status " +
                                 std::to_string(status));
    }}
    return pybind11::bytes(reinterpret_cast<const char*>(data), buffer.getSize());
}}

void busConverterPins(pybind11::module_& m) {{
{pins}
}}

}}  // namespace

#endif
"""

_BUS_PIN = """\
    m.def(
        "bus_{name}",
        []({parameters}) {{
            {bus} value;
{fills}
            return busConverterSerialized(value, "{qualified}");
        }},
        {arguments},
        "F´'s serialization of a {qualified} built from its members' values.");
"""

_ROLE_PIN = """\
    m.def(
        "cdh_{role}",
        [](const pybind11::bytes& bus_bytes) {{
            const std::string text = bus_bytes;
            std::vector<U8> data(text.begin(), text.end());
            Fw::ExternalSerializeBuffer buffer(data.data(), static_cast<FwSizeType>(data.size()));
            buffer.setBuffLen(static_cast<FwSizeType>(data.size()));
            {bus} msg;
            const Fw::SerializeStatus status = msg.deserializeFrom(buffer);
            if (status != Fw::FW_SERIALIZE_OK) {{
                throw std::runtime_error("cdh_{role}: deserializing {qualified} failed with F´ "
                                         "status " + std::to_string(status));
            }}
            return busConverterSerialized(Cdh::BusConverter::convert_{role}(msg), "cdh_{role}");
        }},
        pybind11::arg("bus_bytes"),
        "Role {role}'s bus bytes, deserialized by F´ and converted by Cdh.BusConverter's "
        "generated conversion: F´'s serialization of the {icd} it gives.");
"""


def _bus_pin(model: Model, qualified: str) -> str:
    """The pin building a bus struct from its members' values and returning F´'s serialization.

    Args:
        model: the model.
        qualified: the bus struct's qualified name.

    Returns:
        The pin's `m.def` statement.

    Raises:
        ValueError: a member is not a one-dimensional array of one of `_PRIMITIVES`, naming it.
    """
    bus = model.types[qualified]
    parameters, fills, arguments = [], [], []
    for member in bus.members:
        if member.type not in _PRIMITIVES or member.size is None:
            size = "" if member.size is None else f"[{member.size}] "
            raise ValueError(
                f"{qualified}.{member.name} is {size}{member.type}, which the bus pin does not"
                " take: it takes one-dimensional arrays of the numeric primitives"
            )
        parameters.append(f"const std::array<{member.type}, {member.size}>& {member.name}")
        fills.append(
            f"            for (FwSizeType i = 0; i < {member.size}; i++) {{\n"
            f"                value.get_{member.name}()[i] = {member.name}[i];\n"
            "            }"
        )
        arguments.append(f'pybind11::arg("{member.name}")')
    return _BUS_PIN.format(
        name=qualified.rsplit(".", 1)[-1],
        parameters=", ".join(parameters),
        bus=_cpp(qualified),
        fills="\n".join(fills),
        qualified=qualified,
        arguments=", ".join(arguments),
    )


def _pins(model: Model, found: list[Role]) -> str:
    """The test pins' header: a bus pin per distinct bus struct, and a CDH pin per role.

    Args:
        model: the model.
        found: the roles.

    Returns:
        The header's text.
    """
    buses = dict.fromkeys(role.bus for role in found)
    pins = [_bus_pin(model, bus) for bus in buses]
    pins += [
        _ROLE_PIN.format(role=role.role, bus=_cpp(role.bus), qualified=role.bus, icd=role.icd)
        for role in found
    ]
    return _PINS.format(component=_CONVERTER, pins="\n".join(pins))


def render(model: Model) -> dict[str, str]:
    """The component's C++, from `Cdh.BusConverter`'s roles.

    A role or a field the rule refuses raises `ValueError`, naming it.

    Args:
        model: the model holding the converter and its structs.

    Returns:
        Each file's text, by its name: `BusConverter.hpp`, `BusConverter.cpp` and
        `BusConverterPins.hpp`.
    """
    component = model.components[_CONVERTER]
    base = Path(os.path.relpath(component.file.parent, _REPOSITORY)) / "BusConverterComponentAc.hpp"
    found = roles(model)
    conversions, declarations, definitions = [], [], []
    for role in found:
        conversions.append(
            _CONVERSION.format(
                role=role.role,
                icd=_cpp(role.icd),
                bus=_cpp(role.bus),
                copies="\n".join(_copies(model, role)),
            )
        )
        signature = f"{role.input}_handler(FwIndexType, const {_cpp(role.bus)}& msg)"
        declarations.append(f"    void {signature} override;")
        definitions.append(_HANDLER.format(signature=signature, output=role.output, role=role.role))
    return {
        "BusConverter.hpp": _HEADER.format(
            component=_CONVERTER,
            base=base.as_posix(),
            conversions="".join(conversions),
            declarations="\n".join(declarations),
        ),
        "BusConverter.cpp": _SOURCE.format(component=_CONVERTER, definitions="".join(definitions)),
        "BusConverterPins.hpp": _pins(model, found),
    }


def main(argv: Sequence[str]) -> None:
    """Writes the component's C++ from the contract into a directory.

    Args:
        argv: the directory, alone.
    """
    [directory] = argv
    out = Path(directory)
    out.mkdir(parents=True, exist_ok=True)
    for name, text in render(read(contract_files())).items():
        (out / name).write_text(text)


if __name__ == "__main__":
    main(sys.argv[1:])
