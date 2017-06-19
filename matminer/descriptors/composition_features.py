from pymatgen import Element, Composition, MPRester
import collections
import os
import json

import numpy as np

__author__ = 'Saurabh Bajaj <sbajaj@lbl.gov>'

# TODO: read Magpie file only once
# TODO: Handle dictionaries in case of atomic radii. Aj says "You can require that getting the ionic_radii descriptor
#  requires a valence-decorated Structure or valence-decorated Composition. Otherwise it does not work, i.e. returns
# None. Other radii (e.g. covalent) won't require an oxidation state and people can and should use those for
# non-ionic structures. You can also have a function that returns a mean of ionic_radii for all valences but that
# should not be the default."
# TODO: unit tests
# TODO: most of this code needs to be rewritten ... AJ


# Load elemental cohesive energy data from json file
with open(os.path.join(os.path.dirname(__file__), 'cohesive_energies.json'), 'r') as f:
    ce_data = json.load(f)


def get_pymatgen_descriptor(comp, prop):
    """
    Get descriptor data for elements in a compound from pymatgen.

    Args:
        comp: (str) compound composition, eg: "NaCl"
        prop: (str) pymatgen element attribute, as defined in the Element class at
            http://pymatgen.org/_modules/pymatgen/core/periodic_table.html

    Returns: (list) of values containing descriptor floats for each atom in the compound

    """
    eldata = []
    eldata_tup_lst = []
    eldata_tup = collections.namedtuple('eldata_tup', 'element propname propvalue propunit amt')
    el_amt_dict = Composition(comp).get_el_amt_dict()

    for el in el_amt_dict:

        if callable(getattr(Element(el), prop)) is None:
            raise ValueError('Invalid pymatgen Element attribute(property)')

        if getattr(Element(el), prop) is not None:

            # units are None for these pymatgen descriptors
            # todo: there seem to be a lot more unitless descriptors which are not listed here... -Alex D
            if prop in ['X', 'Z', 'ionic_radii', 'group', 'row', 'number', 'mendeleev_no']:
                units = None
            else:
                units = getattr(Element(el), prop).unit

            # Make a named tuple out of all the available information
            eldata_tup_lst.append(
                eldata_tup(element=el, propname=prop, propvalue=float(getattr(Element(el), prop)), propunit=units,
                           amt=el_amt_dict[el]))

            # Add descriptor values, one for each atom in the compound
            for i in range(int(el_amt_dict[el])):
                eldata.append(float(getattr(Element(el), prop)))

        else:
            eldata_tup_lst.append(eldata_tup(element=el, propname=prop, propvalue=None, propunit=None,
                                             amt=el_amt_dict[el]))

    return eldata


def get_magpie_descriptor(comp, descriptor_name):
    """
    Get descriptor data for elements in a compound from the Magpie data repository.

    Args:
        comp: (str) compound composition, eg: "NaCl"
        descriptor_name: name of Magpie descriptor needed. Find the entire list at
            https://bitbucket.org/wolverton/magpie/src/6ecf8d3b79e03e06ef55c141c350a08fbc8da849/Lookup%20Data/?at=master

    Returns: (list) of descriptor values for each atom in the composition

    """
    data_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", 'magpie_elementdata')
    magpiedata = []
    magpiedata_tup_lst = []
    magpiedata_tup = collections.namedtuple('magpiedata_tup', 'element propname propvalue propunit amt')
    available_props = []

    # Make a list of available properties

    for datafile in os.listdir(data_dir):
        available_props.append(datafile.replace('.table', ''))

    if descriptor_name not in available_props:
        raise ValueError(
            "This descriptor is not available from the Magpie repository. Choose from {}".format(available_props))

    # Get units from Magpie README file
    el_amt = Composition(comp).get_el_amt_dict()
    unit = None
    with open(os.path.join(data_dir, 'README.txt'), 'r') as readme_file:
        readme_file_line = readme_file.readlines()
        for lineno, line in enumerate(readme_file_line, 1):
            if descriptor_name + '.table' in line:
                if 'Units: ' in readme_file_line[lineno + 1]:
                    unit = readme_file_line[lineno + 1].split(':')[1].strip('\n')

    # Extract from data file
    with open(os.path.join(data_dir, '{}.table'.format(descriptor_name)), 'r') as descp_file:
        lines = descp_file.readlines()
        for el in el_amt:
            atomic_no = Element(el).Z
            magpiedata_tup_lst.append(magpiedata_tup(element=el, propname=descriptor_name,
                                                     propvalue=float(lines[atomic_no - 1]), propunit=unit,
                                                     amt=el_amt[el]))

            # Add descriptor values, one for each atom in the compound
            for i in range(int(el_amt[el])):
                magpiedata.append(float(lines[atomic_no - 1]))

    return magpiedata


def get_cohesive_energy(comp):
    """
    Get cohesive energy of compound by subtracting elemental cohesive energies from the formation energy of the compund.
    Elemental cohesive energies are taken from http://www.knowledgedoor.com/2/elements_handbook/cohesive_energy.html.
    Most of them are taken from "Charles Kittel: Introduction to Solid State Physics, 8th edition. Hoboken, NJ:
    John Wiley & Sons, Inc, 2005, p. 50."

    Args:
        comp: (str) compound composition, eg: "NaCl"

    Returns: (float) cohesive energy of compound

    """
    el_amt_dict = Composition(comp).get_el_amt_dict()

    # Get formation energy of most stable structure from MP
    struct_lst = MPRester().get_data(comp)
    if len(struct_lst) > 0:
        struct_lst = sorted(struct_lst, key=lambda e: e['energy_per_atom'])
        most_stable_entry = struct_lst[0]
        formation_energy = most_stable_entry['formation_energy_per_atom']
    else:
        raise ValueError('No structure found in MP for {}'.format(comp))

    # Subtract elemental cohesive energies from formation energy
    cohesive_energy = formation_energy
    for el in el_amt_dict:
        cohesive_energy -= el_amt_dict[el] * ce_data[el]

    return cohesive_energy


def band_center(comp):
    """
    Estimate absolution position of band center using geometric mean of electronegativity
    Ref: Butler, M. a. & Ginley, D. S. Prediction of Flatband Potentials at Semiconductor-Electrolyte Interfaces from
    Atomic Electronegativities. J. Electrochem. Soc. 125, 228 (1978).

    Args:
        comp: (Composition)

    Returns: (float) band center

    """
    prod = 1.0
    for el, amt in comp.get_el_amt_dict().iteritems():
        prod = prod * (Element(el).X ** amt)

    return -prod ** (1 / sum(comp.get_el_amt_dict().values()))


def get_holder_mean(data_lst, power):
    """
    Get Holder mean

    Args:
        data_lst: (list/array) of values
        power: (int/float) non-zero real number

    Returns: Holder mean

    """
    # Function for calculating Geometric mean
    geomean = lambda n: reduce(lambda x, y: x * y, n) ** (1.0 / len(n))

    # If power=0, return geometric mean
    if power == 0:
        return geomean(data_lst)

    else:
        total = 0.0
        for value in data_lst:
            total += value ** power
        return (total / len(data_lst)) ** (1 / float(power))

###Stoichiometric attributes from Ward npj paper
def get_stoich_attributes(comp, p):
    """
    Get stoichiometric attributes

    Args:
        comp: string, e.g "NaCl:
        p:
    
    Returns: 
        Lp norm-based stoichiometric attribute
    """

    el_amt = Composition(comp).get_el_amt_dict()
    
    p_norm = 0
    n_atoms = sum(el_amt.values())

    if p == 0:
        p_norm = n_atoms
    else:
        for i in el_amt:
            p_norm += (el_amt[i]/n_atoms)**p
        p_norm = p_norm**(1.0/p)

    return p_norm

###Elemental properties from Ward npj paper
def get_elem_property_attributes(comp):

    magpie_desc = ["Number", "MendeleevNumber", "AtomicWeight","MeltingT","Column","Row","CovalentRadius","Electronegativity",
        "NsValence","NpValence","NdValence","NfValence","NValance","NsUnfilled","NpUnfilled","NdUnfilled","NfUnfilled","NUnfilled",
        "GSvolume_pa","GSbandgap","GSmagmom","SpaceGroupNumber"]

    all_attributes = []

    for desc in magpie_desc:
        data_lst = get_magpie_descriptor(comp, desc)
        desc_stats = []
        desc_stats.append(min(data_lst))
        desc_stats.append(max(data_lst))
        desc_stats.append(max(data_lst) - min(data_lst))
        desc_stats.append(np.mean(data_lst))
        desc_stats.append(np.std(data_lst))
        desc_stats.append(max(set(data_lst), key=data_lst.count))
        all_attributes.append(desc_stats)

    return all_attributes

def get_frac_weighted_mean(comp, data_lst):
    """Weighted mean of attributes"""

    el_amt = Composition(comp).get_el_amt_dict()
    return el_amt

def get_valence_orbital_attributes(comp):
    """Weighted fraction of valence electrons in each orbital
       Args: 
            comp (string)

       Returns: Fs, Fp, Fd, Ff
    """    
    comp_obj = Composition(comp)
    el_amt = comp_obj.get_el_amt_dict()
    elements = el_amt.keys()
    
    #Fraction weighted total valence electrons
    avg_total_valence = 0
    avg_s = 0
    avg_p = 0
    avg_d = 0
    avg_f = 0

    for f in elements:
        el_frac = comp_obj.get_atomic_fraction(f)
        avg_total_valence += el_frac*get_magpie_descriptor(f,"NValance")[0]
        avg_s += el_frac*get_magpie_descriptor(f,"NsValence")[0]
        avg_p += el_frac*get_magpie_descriptor(f,"NpValence")[0]
        avg_d += el_frac*get_magpie_descriptor(f,"NdValence")[0]
        avg_f += el_frac*get_magpie_descriptor(f,"NfValence")[0]

    Fs = avg_s/avg_total_valence
    Fp = avg_p/avg_total_valence
    Fd = avg_d/avg_total_valence
    Ff = avg_f/avg_total_valence

    return Fs, Fp, Fd, Ff

def get_ionic_attributes(comp):
    """
    Ionic character
    """
    ##Issue reading OxidationStates file...
    comp_obj = Composition(comp)
    el_amt = comp_obj.get_el_amt_dict()
    elements = el_amt.keys()
    values = el_amt.values()
    
    import itertools
    
    atom_pairs = itertools.combinations(elements, 2)

    ionic_char = []
    avg_ionic_char = 0

    for pair in atom_pairs:
        XA = get_magpie_descriptor(pair[0], "Electronegativity")
        XB = get_magpie_descriptor(pair[1], "Electronegativity")
        ionic_char.append(1.0 - np.exp(-0.25*(np.array(XA)-np.array(XB))**2))
        avg_ionic_char += comp_obj.get_atomic_fraction(pair[0])*comp_obj.get_atomic_fraction(pair[1])*ionic_char[-1]    
    
    max_ionic_char = np.max(ionic_char)
 
    return max_ionic_char, avg_ionic_char[0]

if __name__ == '__main__':
    descriptors = ['atomic_mass', 'X', 'Z', 'thermal_conductivity', 'melting_point',
                   'coefficient_of_linear_thermal_expansion']

    for desc in descriptors:
        print(get_pymatgen_descriptor('LiFePO4', desc))
    print(get_magpie_descriptor('LiFePO4', 'AtomicVolume'))
    print(get_magpie_descriptor('LiFePO4', 'Density'))
    print(get_holder_mean([1, 2, 3, 4], 0))


    ####TESTING WARD NPJ DESCRIPTORS
    print "WARD NPJ ATTRIBUTES"
    print "Stoichiometric attributes"
    print get_stoich_attributes("Fe2O3", 3)
    print "Elemental property attributes"
    print get_elem_property_attributes("Fe2O3")
    print "Valence Orbital Attributes"
    print get_valence_orbital_attributes("Fe2O3")
    print "Ionic attributes"
    print get_ionic_attributes("Fe2O3")
