from flask import Flask, jsonify, request, abort
from flask_cors import CORS
from flask_restful import Resource, Api
import joblib
import pymongo
from pymongo import MongoClient
from bson.objectid import ObjectId
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from os import getenv


client = pymongo.MongoClient(getenv('MONGODB_URI'))
db = client.jobmatching
applicants = db.applicants
users = db.users
postings = db.postings
companies = db.companies

app = Flask(__name__)
CORS(app)
api = Api(app)

classifier = joblib.load('model.joblib')
vectorizer = TfidfVectorizer()

class Postings(Resource):
    def post(self):
        json_data = request.get_json(force=True)
        job_title = json_data["job_title"]
        posting_skills = json_data["posting_skills"]
        username = json_data["username"]
        suitable_candidates = list()
        for applicant in applicants.find({}):
            id = str(applicant['_id'])
            yoe = applicant['yoe']
            skills = vectorizer.fit_transform([applicant['applicant_skills'], posting_skills])
            skills_similarity = cosine_similarity(skills[0:1], skills)[0][1]
            if yoe == 0:
                input_vector = np.array([0, 0, 0])
            elif yoe == 1:
                input_vector = np.array([1, 0, 0])
            elif yoe == 2:
                input_vector = np.array([0, 1, 0])
            else:
                input_vector = np.array([0, 0, 1])
            input_vector = np.append(input_vector, skills_similarity)
            prediction = classifier.predict(input_vector.reshape(1, -1))
            if (prediction == 1):
                suitable_candidates.append(id)
        posting_id = postings.insert_one({"job_title": job_title, "posting_skills": posting_skills, "suitable_candidates": suitable_candidates}).inserted_id
        company = companies.find_one({"username": username})
        company_postings = company["postings"]
        company_postings.append(posting_id)
        companies.update_one({"username": username}, {"$set": {"postings": company_postings}})
        return jsonify(job_title=job_title, posting_skills=posting_skills, suitable_candidates=suitable_candidates, posting_id=str(posting_id))

class PostingsQuery(Resource):
    def get(self, id):
        posting = postings.find_one({"_id": ObjectId(id)})
        suitable_candidate_ids = posting["suitable_candidates"]
        suitable_candidates = list()
        for candidate_id in suitable_candidate_ids:
            candidate = applicants.find_one({'_id': ObjectId(candidate_id)})
            suitable_candidates.append({"yoe": candidate["yoe"], "applicant_skills": candidate["applicant_skills"]})
        return jsonify(job_title=posting["job_title"], posting_skills=posting["posting_skills"], suitable_candidates=suitable_candidates)

class ApplicantsQuery(Resource):
    def get(self, id):
        applicant = applicants.find_one({"_id": ObjectId(id)})
        return jsonify(yoe=applicant["yoe"], applicant_skills=applicant["applicant_skills"])

class Applicants(Resource):
    def post(self):
        json_data = request.get_json(force=True)
        yoe = json_data["yoe"]
        applicant_skills = json_data["applicant_skills"]
        username = json_data["username"]
        applicant_id = applicants.insert_one({"yoe": yoe, "applicant_skills": applicant_skills}).inserted_id
        users.update_one({"username": username}, {"$set": {"application": applicant_id}})
        if yoe == 0:
            input_vector = np.array([0, 0, 0])
        elif yoe == 1:
            input_vector = np.array([1, 0, 0])
        elif yoe == 2:
            input_vector = np.array([0, 1, 0])
        else:
            input_vector = np.array([0, 0, 1])
        posting_list = list()
        for posting in postings.find({}):
            posting_list.append(posting)
        for posting in posting_list:
            id = str(posting['_id'])
            suitable_candidates = posting['suitable_candidates']
            posting_skills = posting['posting_skills']
            job_title = posting['job_title']
            skills = vectorizer.fit_transform([applicant_skills, posting_skills])
            skills_similarity = cosine_similarity(skills[0:1], skills)[0][1]
            input_vector = np.append(input_vector, skills_similarity)
            prediction = classifier.predict(input_vector.reshape(1, -1))
            if (prediction == 1):
                suitable_candidates.append(str(applicant_id))
                postings.update_one({"_id": ObjectId(id)}, {"$set": {"suitable_candidates": suitable_candidates}})
        return jsonify(yoe=yoe, applicant_skills=applicant_skills, applicant_id=str(applicant_id))

class SignupApplicant(Resource):
    def post(self):
        json_data = request.get_json(force=True)
        username = json_data["username"]
        password = json_data["password"]
        curr_user = users.find_one({"username": username})
        if (curr_user == None):
            users.insert_one({"username": username, "password": password, "application": ""})
        else:
            abort(409, description="A user with that username already exists.")

class SignupCompany(Resource):
    def post(self):
        json_data = request.get_json(force=True)
        username = json_data["username"]
        password = json_data["password"]
        curr_company = companies.find_one({"username": username})
        if (curr_company == None):
            companies.insert_one({"username": username, "password": password, "postings": []})
        else:
            abort(409, description="A company with that username already exists.")
        
class LoginApplicant(Resource):
    def post(self):
        json_data = request.get_json(force=True)
        username = json_data["username"]
        password = json_data["password"]
        curr_user = users.find_one({"username": username})
        if (curr_user != None and password == curr_user["password"]):
            return jsonify(user=username, application=str(curr_user["application"]))
        else:
            abort(403, description="Wrong password or wrong username")

class LoginCompany(Resource):
    def post(self):
        json_data = request.get_json(force=True)
        username = json_data["username"]
        password = json_data["password"]
        curr_company = companies.find_one({"username": username})
        if (curr_company != None and password == curr_company["password"]):
            result = list()
            for i in range(len(curr_company["postings"])):
                result.append(str(curr_company["postings"][i]))
            return jsonify(user=username, postings=result)
        else:
            abort(403, description="Wrong password or wrong username")

class HelloWorld(Resource):
    def get(self):
        return {"hello": "world"}

api.add_resource(HelloWorld, '/')
api.add_resource(SignupApplicant, '/signupapplicant')
api.add_resource(SignupCompany, '/signupcompany')
api.add_resource(LoginApplicant, '/loginapplicant')
api.add_resource(LoginCompany, '/logincompany')
api.add_resource(Applicants, '/applicants')
api.add_resource(ApplicantsQuery, '/applicants/<string:id>')
api.add_resource(Postings, '/postings')
api.add_resource(PostingsQuery, '/postings/<string:id>')

if __name__ == '__main__':
    app.run(debug=True)
