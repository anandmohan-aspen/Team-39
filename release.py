#!/usr/bin/env python3

from argparse import ArgumentParser
import logging
import subprocess
from pathlib import Path
import re
import requests
import configparser
import base64
import os

def run_git_command(command):
    logging.info(f"Running command: {command}")
    
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    
    output = stdout.decode("utf-8").strip()
    error = stderr.decode("utf-8").strip()
    
    if output:
        logging.info(output)
    if error:
        logging.error(error)

    if process.returncode != 0:
        raise subprocess.CalledProcessError(
            process.returncode, 
            command, 
            output=output, 
            stderr=error
        )
    return output

def create_git_tag(tag_name, dry_run):
    if dry_run == "true":
        logging.info(f"Dry Run - Running git tag -m {tag_name} {tag_name}")
    else:
        commit_hs = run_git_command(["git", "rev-parse", "HEAD"])
        head_ = commit_hs[:10]
        run_git_command(["git", "tag",  tag_name, head_])
        run_git_command(["git", "push", "origin", tag_name])
        logging.info(f"created new tag {tag_name}")

def create_git_branch(branch_name, dry_run):
    if dry_run == "true":
        logging.info(f"Dry Run - Creating Branch {branch_name}")
    else:
        commit_hs = run_git_command(["git", "rev-parse", "HEAD"])
        head_ = commit_hs[:10]
        run_git_command(['git', 'checkout', head_])
        run_git_command(['git', 'push', 'origin', 'HEAD:refs/heads/' + branch_name]) 
        logging.info(f"created new branch {branch_name}")

def push_version_changes(branch_name, version_to_release, next_version, sorted_matched_files, dry_run):
    if dry_run == "true":
        logging.info(f"Dry Run - Pushing version changes to  {branch_name}")
    else:
        for p in sorted_matched_files:
           logging.info(f"Running git add {p}")
           run_git_command(["git", "add", p])
        run_git_command(["git", "commit", "-m",  f"Updating version from {version_to_release} to {next_version}"])
        run_git_command(["git", "push", "origin", 'HEAD:refs/heads/hackathon'])

def push_prerelease_flag(branch_name, prerelease_flag, sorted_matched_files, dry_run):
    if dry_run == "true":
        logging.info(f"Dry Run - Updating prerelease flag to  {prerelease_flag}")
    else:
        for p in sorted_matched_files:
           run_git_command(["git", "add", p])
        run_git_command(["git", "commit", "-m", f"Updating prerelease flag to  {prerelease_flag}"])
        run_git_command(["git", "push", "origin", "HEAD:" + branch_name])

def update_versions_in_repo(branch_name, version_to_release, next_version, dry_run):
    root_directory = Path(".").absolute()
    filenames_to_search = ['branch.properties', 'mRelease.h'] 
    sorted_matched_files = sorted_files_by_filenames(root_directory, filenames_to_search)
    for p in sorted_matched_files:
        replace_version(p, next_version)
    push_version_changes(branch_name, version_to_release, next_version, sorted_matched_files, dry_run)

def update_pre_release_for_MORE(prerelease_flag, branch_name, dry_run):
    run_git_command(['git', 'checkout', branch_name])
    run_git_command(['git', 'pull', 'origin', branch_name])
    root_directory = Path(".").absolute()
    filenames_to_search = ['branch.properties'] 
    sorted_matched_files = sorted_files_by_filenames(root_directory, filenames_to_search)
    for p in sorted_matched_files:
        replace_prerelease(p, prerelease_flag)
    push_prerelease_flag(branch_name, prerelease_flag, sorted_matched_files, dry_run)

def replace_prerelease(pipeline_file: Path, new_version):
    """
    Replace versions in various files
    """
    file = pipeline_file
    file_content = file.read_text()

    replacements = {
        (r'more_prerelease=\d', f'more_prerelease={new_version}'),  # Replace more_prerelease flag
    }
    for pattern, replacement in replacements:
            file_content = re.sub(pattern, replacement, file_content)
    file.write_text(file_content)
    return True

def replace_version(pipeline_file: Path, new_version):
    """
    Replace versions in various files
    """
    file = pipeline_file
    majorversion1 = new_version.split('.')[0]
    majorversion2 = new_version.split('.')[1]
    majorversion = majorversion1 + '.' + majorversion2
    cpversion = new_version.split('.')[2]
    epversion = new_version.split('.')[3] 
    newlicenseversion = majorversion1 + majorversion2 + cpversion + epversion + "00"
    newlogversion = '{"' + "V" + majorversion + '"}'
    file_content = file.read_text()
    
    replacements = {
        (r'versionmajor=\b\d{2}\b\.\d', f'versionmajor={majorversion}'),
        (r'version_ = \b\d{7}\b', f'version_ = {newlicenseversion}'), 
        (r'cVersion_=\{\s*"V\d+\.\d+"\s*\}', f'cVersion_={newlogversion}'),
    }
    for pattern, replacement in replacements:
        file_content = re.sub(pattern, replacement, file_content)
    file.write_text(file_content)
    return True

def sorted_files_by_filenames(root_dir, filenames):
    # Convert root directory to Path object
    root = Path(root_dir)

    # Create a list of matched files for each filename
    matched_files = []
    for filename in filenames:
        matched_files.extend(root.rglob(filename))  # Search recursively for each filename

    # Sort the matched files based on their names
    sorted_files = sorted(matched_files)

    return sorted_files

def get_repository_id(api_url, personal_access_token) -> str:
    """
    Retrieve the ID of the given repository.
    """
    # Send a GET request to the Azure DevOps API to retrieve repository information
    response = requests.get(api_url, auth=("", personal_access_token))
    response.raise_for_status()

    # Extract the repository ID from the request response
    repository_id = response.json()['id']
    return repository_id

def create_pipeline_definition(repo_name, repo_id, yaml_file):
    """
    Function to create a pipeline definition from a YAML file
    """
    pipeline_definition = {
        "name": 'more-pipeline-nightly-14.5',
        'folder': '\\Demo\\MORE',
        "configuration": {
            "type": "yaml",
            "repository": {
                "id": repo_id,
                "name": repo_name,
                "type": "azureReposGit"
            },
            "path": yaml_file
        }
    }
    return pipeline_definition


def create_pipeline(pipeline_definition, api_url, personal_access_token, dry_run) -> bool:
    """
    Function to create a pipeline
    """
   
    b64_token = base64.b64encode(f":{personal_access_token}".encode()).decode()

    HEADERS = {
        'Content-Type': 'application/json',
        'Authorization': f'Basic {b64_token}'
    }

    if dry_run == "true":
        logging.info(f"Dry Run - Created pipeline with this definition: {pipeline_definition}")
    else:
        # Send a POST request to the Azure DevOps API to create the pipeline
        response = requests.post(
            api_url,
            json=pipeline_definition,
            headers=HEADERS,
        )

        if response.status_code == 400:
            logging.warning(response.text)
        elif response.status_code == 409:
            logging.warning(response.text)
        else: 
            logging.warning(response.text)

        try:
            # Extract the pipeline ID from the request response
            pipeline_id = response.json()['id']

            # Display a message to the user
            logging.info(f"The pipeline has been created successfully. ID: {pipeline_id}")
        except KeyError as e:
            logging.error(f"KeyError in json : {str(e)} for {pipeline_definition}")
            return False
        return True

def parse_cli_options() -> (dict):
    parser = ArgumentParser()
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Do not do the release , but log things.",
    )
    parser.add_argument(
        "--release_type",
        type=str,
        help="Example --release_type (prerelease, major, ep, cp)",
    ) 
    parser.add_argument(
        "--version_to_release",
        type=str,
        help="Example --version 15.0.0.0",
    )
    parser.add_argument(
        "--next_version",
        type=str,
        help="Example --version 15.1.0.0",
    )    
    result = parser.parse_args()
    return result

def trigger_release_build(branch_name, version_to_release, next_version, release_type, dry_run):
    if dry_run == "true":
        logging.info(f"Dry Run - Triggering release build  {version_to_release}")
    else:
        logging.info("Running trigger")
        ACCESS_TOKEN = "need to add this"
        b64_token = base64.b64encode(f":{ACCESS_TOKEN}".encode()).decode()
        HEADERS = {
        'Content-Type': 'application/json',
        'Authorization': f'Basic {b64_token}'
        }
        url = f"https://dev.azure.com/pdgm/Sandbox/_apis/pipelines/979/runs?api-version=7.1"
        data = {
                "resources": {
                            "repositories": {
                                "self": {
                                    "refName": f"refs/tags/{version_to_release}"
                                }
                            }
                        }
                }
        try:
           response = requests.post(url, headers=HEADERS, json=data)
           if response.status_code == 200:
               logging.info(f"Triggered release build for {version_to_release}")
           else:
               logging.info(f"Failed to trigger: {response.status_code}")             
        except Exception as e:
           logging.error(f"Failed to trigger build {e}")
           raise()

def main() -> int:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s | %(message)s')
    logging.info("Parsing options.")
    (options) = parse_cli_options()

    if options.dry_run:
        dry_run = "true"
    else:
        dry_run = "false"
    version_to_release = options.version_to_release
    next_version = options.next_version
    release_type = options.release_type

    # The following are needed for pipeline creation

    yaml_file = "azure-pipelines-nightly.yml"
    config = configparser.ConfigParser()
    config.read('config.ini')
    organization_url = config.get('API', 'organization_url')
    project_name = config.get('API', 'project_name')
    personal_access_token = config.get('API', 'personal_access_token')
    api_version = config.get('API', 'api_version')
    repo =  config.get('API', 'repo_name')
    # Retrieve repository id
    # Create the Azure DevOps API URL to retrieve repository information
    api_url_repo = f"{organization_url}/{project_name}/_apis/git/repositories/{repo}?api-version={api_version}"

    repository_id = get_repository_id(api_url_repo, personal_access_token)
    # Display the repository ID
    logging.info(f"The repository ID is: {repository_id}")

    # Deploy the new pipeline
    logging.info("Starting deployment...")

    api_url_pipeline = f"{organization_url}/{project_name}/_apis/pipelines?api-version={api_version}"
    logging.info (api_url_pipeline)
    pipeline_definition = create_pipeline_definition(repo, repository_id, yaml_file)
    branch_name = "V" + version_to_release.split('.')[0] + "." + version_to_release.split('.')[1]
    try:
        if release_type == "prerelease":
            logging.info (f"Running prerelease {dry_run}")
            # tag MAIN to 15.0
            tag_ = version_to_release.split('.')[0] + "." + version_to_release.split('.')[1]
            create_git_tag(tag_, dry_run)
            # create V15.0 branch
            create_git_branch(branch_name, dry_run)
            update_versions_in_repo(branch_name, version_to_release, next_version, dry_run)
            create_git_tag(next_version + "-snapshot", dry_run)
            # create a nightly pipeline for V15.0 and trigger 
            # Creating api url for pipeline
            create_pipeline(pipeline_definition, api_url_pipeline, personal_access_token, dry_run)
            

        elif release_type == "major":
            logging.info(f"Creating {release_type} release {version_to_release}")
            # change prerelease to 0
            update_pre_release_for_MORE('0', branch_name, dry_run)
            # tag 15.0.0.0
            create_git_tag(version_to_release, dry_run)
            trigger_release_build(branch_name, version_to_release, next_version, release_type, dry_run)
            # change prerelease to 1
            update_pre_release_for_MORE('1', branch_name, dry_run)
        else:
            # For ep and cp
            logging.info(f"Creating {release_type} release {version_to_release}")
            # change prerelease to 0
            update_pre_release_for_MORE('0', branch_name, dry_run)
            # tag 15.0.0.1
            create_git_tag(version_to_release, dry_run)
            trigger_release_build(branch_name, version_to_release, next_version, release_type, dry_run)
            # change prerelease to 1
            update_pre_release_for_MORE('1', branch_name, dry_run)
    except Exception as e:
        # Uncomment for local debugging
        #traceback.print_exc()
        logging.error (f"Something went wrong {e}")
        raise()

if __name__ == "__main__":
    exit(main())
