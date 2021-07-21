from flask import jsonify, request, abort
from flask.views import MethodView
from flask_login import current_user
from typing import List
from webargs import fields, validate
from webargs.flaskparser import parser, use_args, use_kwargs

from app import db
from app.models import Course, CourseUserAttended, User
from app.schemas import (
    CourseSchema,
    NewUserLocation,
    NewUserSchema,
    UserAttendingSchema,
    UserLocationSchema,
    UserSchema,
)


class UserListAPI(MethodView):
    @parser.use_kwargs({'user_type': fields.Int()}, location="querystring")
    def get(self: None, user_type=None) -> List[User]:
        """ Get a list of all users.

        Returns:
            List[User]: List of users.
        """

        print(user_type is None)
        print(current_user.usertype_id == 1)
        print(current_user.usertype_id == 1 and user_type is None)
        # TODO: Clean this up somehow?
        if current_user.usertype_id == 4:
            print('Teacher')
            abort(401)
        elif current_user.usertype_id != 1 and user_type is None:
            print('Not a teacher or admin')
            # abort a request from non-admins for all users
            abort(401)
        elif current_user.usertype_id < 4 and current_user.usertype_id != 1 and user_type != 1:
            print('Not a teacher, not requesting an admin')
            # presenters, observers, and admins can request non-admins
            users = User.query.filter_by(usertype_id=user_type).all()
        elif current_user.usertype_id == 1 and user_type:
            print('Admin looking for a specfic type')
            users = User.query.filter_by(usertype_id=user_type).all()
        elif current_user.usertype_id == 1 and user_type is None:
            print('Admin looking for all users')
            users = User.query.all()
            print(users)
        else:
            abort(422)

        return jsonify(UserSchema(many=True).dump(users))

    def post(self: None) -> User:
        """ Create a new user

        Returns:
            User: JSON representation of the user
        """
        args = parser.parse(NewUserSchema(), location="json")

        try:
            user = User().create(User, args)
            result = User.query.get(user.id)
            return jsonify(UserSchema().dump(result))
        except Exception as e:
            return jsonify(e)


class UserAPI(MethodView):
    def get(self: None, user_id: int) -> User:
        """Get a single user

        Args:
            user_id (int): valid user ID

        Returns:
            User: JSON representation of the user.
        """

        # Limit this to SuperAdmin, Presenters, or the user making the request
        if current_user.usertype_id != 1 or current_user.usertype_id != 2 or user_id is not current_user.id:
            abort(401)
        user = User.query.get(user_id)
        return jsonify(UserSchema().dump(user))

    def put(self: None, user_id: int) -> User:
        """ Update a user's details

        Args:
            user_id (int): valid user ID

        Returns:
            User: updated user as JSON
        """

        # Limit this to SuperAdmins or the user making the request.
        if current_user.usertype_id != 1:
            abort(401)

        args = parser.parse(UserSchema(), location="json")
        user = User.query.get(user_id)
        if user is None:
            abort(404)

        try:
            user.update(args)
            return jsonify(UserSchema().dump(user))
        except Exception as e:
            return jsonify(e)

    def delete(self: None, user_id: int) -> dict:
        """ Delete a user.

        Deletion will cascade through the database and remove their records
        of attendance, registrations, and presentations. Be careful.

        Args:
            user_id (int): valid user ID

        Returns:
            dict: status of the deletion.
        """
        if current_user.usertype_id != 1:
            abort(401)

        args = parser.parse(UserSchema(), location="query")
        user = User.query.get(user_id)

        if user is None:
            abort(404)

        try:
            db.session.delete(user)
            db.session.commit()

            return jsonify({"message": "Delete successful."})
        except Exception as e:
            return jsonify(e)


class UserLocationAPI(MethodView):
    def get(self: None, user_id: int) -> User:
        """ Get a user's location

        Args:
            user_id (int): valid user ID

        Returns:
            User: user location as JSON
        """
        user = User.query.get(user_id)
        if user is None:
            abort(404)

        return jsonify(UserLocationSchema().dump(user.location))

    def post(self: None, user_id: int) -> User:
        """ Update a user's location

        Args:
            user_id (int): valid user ID

        Returns:
            User: Updated user location as JSON
        """
        args = parser.parse(NewUserLocation(), location="json")
        user = User.query.get(user_id)
        if user is None:
            abort(404)

        try:
            user.update(args)
            return jsonify(UserLocationSchema().dump(user.location))
        except Exception as e:
            return jsonify(e)

    def delete(self: None, user_id: int) -> User:
        """ Delete a user's location

        Args:
            user_id (int): valid user ID

        Returns:
            User: User as JSON
        """
        user = User.query.get(user_id)
        if user is None:
            abort(404)

        user.location = None
        db.session.commit()

        return jsonify(UserLocationSchema().dump(user.location))


class UserAttendingAPI(MethodView):
    def get(self: None, user_id: int) -> List[Course]:
        """ Get events where user is listed as an attendee.

        Args:
            user_id (int): valid user ID

        Returns:
            List[Course]: list of courses
        """
        if user_id is not current_user.id:
            abort(401)

        user = User.query.get(user_id)
        if user is None:
            abort(404)

        return jsonify(UserAttendingSchema(many=True).dump(user.registrations))

class UserConfirmedAPI(MethodView):
    # Return only _confirmed_ courses for a user
    def get(self: None, user_id: int) -> List[Course]:
        """ Get a list of sessions for which the user's attendance has been confirmed.

        Args:
            user_id (int): User ID

        Returns:
            List[Course]: List of <Course> objects as JSON
        """
        if user_id is not current_user.id:
            abort(401)

        confirmed = CourseUserAttended.query.filter_by(user_id=user_id, attended=1).all()
        if confirmed is None:
            abort(404)

        for event in confirmed:
            event.course.total = divmod((event.course.ends - event.course.starts).total_seconds(), 3600)[0]

        return jsonify(UserAttendingSchema(many=True).dump(confirmed))


class UserPresentingAPI(MethodView):
    # Show courses a user is presenting
    def get(self: None, user_id: int) -> List[Course]:
        """ Return a list of Courses where the user_id is listed as a presenter.

        Args:
            user_id (int): User ID

        Returns:
            List[Course]: List of <Course> objects as JSON
        """
        if user_id is not current_user.id:
            abort(401)

        user = User.query.get(user_id)
        if user is None:
            abort(404)
        return jsonify(CourseSchema(many=True).dump(user.presenting))
