import streamlit as st

absolute_zero = -273.25
fahrenheit_gradient = 9.0 / 5.0


def calc_fahrenheit(celsius):
    return fahrenheit_gradient * celsius + 32


def calc_celsius_from_fahrenheit(fahrenheit):
    return (fahrenheit - 32) / fahrenheit_gradient


starting_value = 0
state = st.state.get(celsius=starting_value, fahrenheit=calc_fahrenheit(starting_value))


min_value = absolute_zero
max_value = 300
step = 0.25

st.slider(
    "Celsius",
    # Build the widget objects to be "state aware", as in, if a state
    # object is passed as a value, have the widget respond automatically
    # to state updates
    value=state.celsius,
    min_value=min_value,
    max_value=max_value,
    step=step,
)

st.slider(
    "Fahrenheit",
    value=state.fahrenheit,
    min_value=calc_fahrenheit(min_value),
    max_value=calc_fahrenheit(max_value),
    step=fahrenheit_gradient * step,
)

# Have the "link_to" function create a directional 'master' graph. Make
# it so that on each UI trigger the links/edges on that master graph are
# traversed, all the while building a record of the traversed links in
# a directional acyclic graph. When traversing these links should any
# traversal along an edge on the 'master' graph causes a cycle, have
# that edge not be traversed for that particular UI interaction.
state.celsius.link_to(state.fahrenheit, calc_fahrenheit)
state.fahrenheit.link_to(state.celsius, calc_celsius_from_fahrenheit)

# Example flow:

# * User triggers the fahrenheit slider
# * state.fahrenheit updated
# * state.celsius to updated by state.fahrenheit -> state.celsius link
#   * importantly, the state.celsius -> state.fahrenheit is not triggered
#     as this is the first step in the chain that produces a cycle in the
#     link graph. These links can be propagated and carried out until no
#     more links remain, or following a link would produce a cycle for
#     that iteration.
# * this triggers celsius slider to update


# ---------------------------------------------------------------------
# To decouple different sections of a streamlit app, it can be spread
# over multiple Python files, the `st.state.get` object can be called
# a second time in the same streamlit session


def calc_celsius_from_kelvin(kelvin):
    return kelvin + absolute_zero


def calc_kelvin(celsius):
    return celsius - absolute_zero


# This will error out if the state.get function hasn't been previously
# called with a celsius **kwarg passed to it. Also, it is okay to add
# items to the state method call that weren't passed previously.
another_state_object = st.state.get("celsius", kelvin=calc_kelvin(starting_value))


st.slider(
    "Kelvin",
    value=another_state_object.kelvin,
    min_value=calc_kelvin(min_value),
    max_value=calc_kelvin(max_value),
    step=step,
)

another_state_object.kelvin.link_to(
    another_state_object.celsius, calc_celsius_from_kelvin
)

# Importantly, the directional 'master' graph is defined each run. The
# master graph can change between reruns:
if st.checkbox("Auto update Kelvin?"):
    # Why someone would want to unlink the kelvin slider... I don't
    # know. But... for the example :).
    another_state_object.celsius.link_to(another_state_object.kelvin, calc_kelvin)


if st.button("Take me to absolute zero!"):
    another_state_object.kelvin.update(0)


st.write(
    f"""
        Overview:

        * Celsius: `{state.celsius.value}`
        * Fahrenheit: `{state.fahrenheit.value}`
        * Kelvin: `{another_state_object.kelvin.value}`

    """
)
