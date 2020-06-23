#!/usr/bin/env python3

"""
This script should use a very simple, functional programming style.
Avoid Jinja macros in favor of native Python functions.

Don't go overboard on code generation; use Python only to generate
content that can't be easily declared statically using CircleCI's YAML API.

Data declarations (e.g. the nested loops for defining the configuration matrix)
should be at the top of the file for easy updating.

See this comment for design rationale:
https://github.com/pytorch/vision/pull/1321#issuecomment-531033978
"""

import jinja2
import yaml
import os.path


PYTHON_VERSIONS = ["3.6", "3.7", "3.8"]


def build_workflows(prefix='', upload=False, filter_branch=None, indentation=6):
    w = []
    w += build_download_job(filter_branch)
    for btype in ["wheel", "conda"]:
        for os_type in ["linux", "macos", "windows"]:
            for python_version in PYTHON_VERSIONS:
                w += build_workflow_pair(btype, os_type, python_version, filter_branch, prefix, upload)

    return indent(indentation, w)


def build_download_job(filter_branch):
    job = {
        "name": "download_third_parties_nix",
    }

    if filter_branch:
        job["filters"] = gen_filter_branch_tree(filter_branch)
    return [{"download_third_parties_nix": job}]


def build_workflow_pair(btype, os_type, python_version, filter_branch, prefix='', upload=False):

    w = []
    base_workflow_name = "{prefix}binary_{os_type}_{btype}_py{python_version}".format(
        prefix=prefix,
        os_type=os_type,
        btype=btype,
        python_version=python_version,
    )

    w.append(generate_base_workflow(base_workflow_name, python_version, filter_branch, os_type, btype))

    if upload:

        is_py3_linux = os_type in ['linux', "windows"] and not python_version.startswith("2.")

        w.append(generate_upload_workflow(base_workflow_name, filter_branch, btype))

        if filter_branch == 'nightly' and is_py3_linux:
            pydistro = 'pip' if btype == 'wheel' else 'conda'
            w.append(generate_smoketest_workflow(pydistro, base_workflow_name, filter_branch, python_version, os_type))

    return w


def generate_base_workflow(base_workflow_name, python_version, filter_branch, os_type, btype):

    d = {
        "name": base_workflow_name,
        "python_version": python_version,
    }

    if os_type in ['linux', 'macos']:
        d['requires'] = ['download_third_parties_nix']

    if filter_branch:
        d["filters"] = gen_filter_branch_tree(filter_branch)

    return {"binary_{os_type}_{btype}".format(os_type=os_type, btype=btype): d}


def gen_filter_branch_tree(*branches):
    return {
        "branches": {
            "only": list(branches),
        },
        "tags": {
            # Using a raw string here to avoid having to escape
            # anything
            "only": r"/v[0-9]+(\.[0-9]+)*-rc[0-9]+/"
        }
    }


def generate_upload_workflow(base_workflow_name, filter_branch, btype):
    d = {
        "name": "{base_workflow_name}_upload".format(base_workflow_name=base_workflow_name),
        "context": "org-member",
        "requires": [base_workflow_name],
    }

    if filter_branch:
        d["filters"] = gen_filter_branch_tree(filter_branch)

    return {"binary_{btype}_upload".format(btype=btype): d}


def generate_smoketest_workflow(pydistro, base_workflow_name, filter_branch, python_version, os_type):

    required_build_suffix = "_upload"
    required_build_name = base_workflow_name + required_build_suffix

    smoke_suffix = "smoke_test_{pydistro}".format(pydistro=pydistro)
    d = {
        "name": "{base_workflow_name}_{smoke_suffix}".format(
            base_workflow_name=base_workflow_name, smoke_suffix=smoke_suffix),
        "requires": [required_build_name],
        "python_version": python_version,
    }

    if filter_branch:
        d["filters"] = gen_filter_branch_tree(filter_branch)

    return {"smoke_test_{os_type}_{pydistro}".format(os_type=os_type, pydistro=pydistro): d}


def indent(indentation, data_list):
    return ("\n" + " " * indentation).join(yaml.dump(data_list).splitlines())


def unittest_workflows(indentation=6):
    jobs = []
    jobs += build_download_job(None)
    for os_type in ["linux", "windows"]:
        for device_type in ["cpu", "gpu"]:
            for i, python_version in enumerate(PYTHON_VERSIONS):
                job = {
                    "name": f"unittest_{os_type}_{device_type}_py{python_version}",
                    "python_version": python_version,
                }

                if device_type == 'gpu':
                    job['filters'] = gen_filter_branch_tree('master', 'nightly')

                if os_type != "windows":
                    job['requires'] = ['download_third_parties_nix']

                jobs.append({f"unittest_{os_type}_{device_type}": job})

                if i == 0 and os_type == "linux" and device_type == "cpu":
                    jobs.append({
                        f"stylecheck": {
                            "name": f"stylecheck_py{python_version}",
                            "python_version": python_version,
                        }
                    })
    return indent(indentation, jobs)


if __name__ == "__main__":
    d = os.path.dirname(__file__)
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(d),
        lstrip_blocks=True,
        autoescape=False,
    )

    with open(os.path.join(d, 'config.yml'), 'w') as f:
        f.write(env.get_template('config.yml.in').render(
            build_workflows=build_workflows,
            unittest_workflows=unittest_workflows,
        ))